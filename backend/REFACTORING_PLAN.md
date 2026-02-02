# Refactoring Plan: Move MH-Specific Content to Configuration

## Goal
Move all domain-specific content from Python code to `domain_config.yaml` so that:
- **0% MH-specific code** in Python files
- **100% domain logic** in YAML config
- Switching domains = replacing one YAML file

---

## Changes Required

### 1. chat.py - SALES_ASSISTANT_SYSTEM_PROMPT

**Current:** 160 lines hardcoded prompt with:
- Material corrosion table (FZ/ZM/RF)
- Environment requirements (hospital, marine, food)
- Widget selection rules

**Refactor to:**

```python
# chat.py
from config_loader import get_config

config = get_config()
SALES_ASSISTANT_SYSTEM_PROMPT = config.prompts.sales_assistant.format(
    material_rules=config.get_material_rules_prompt(),
    environment_rules=config.get_environment_rules_prompt(),
    widget_rules=config.get_widget_rules_prompt()
)
```

**Add to domain_config.yaml:**

```yaml
prompts:
  sales_assistant: |
    You are a middleware between a Knowledge Graph and a React UI for {domain.company}.

    ## CRITICAL: LANGUAGE REQUIREMENT
    **ALL responses MUST be in ENGLISH.**

    ## WIDGET SELECTION RULES
    ### 1. SAFETY_GUARD Widget (HIGHEST PRIORITY)
    Use when detecting safety/compliance risks defined in safety_rules below.

    ### 1b. SPECIFICATION-ENVIRONMENT MISMATCH
    {material_environment_rules}

    ### 1c. CLARIFICATION MODE
    {clarification_rules}

    [... rest of prompt ...]

# Domain-specific rules that get injected
material_environment_rules:
  hierarchy:
    - code: "FZ"
      name: "Galvanized Steel"
      class: "C3"
      description: "Standard indoor, mild environments"
    - code: "ZM"
      name: "Zinc-Magnesium"
      class: "C4"
      description: "Moderate environments"
    - code: "RF"
      name: "Stainless Steel"
      class: "C5"
      description: "Demanding: healthcare, food, wet, chemical"

  environments:
    demanding:
      - name: "hospital"
        aliases: ["medical", "healthcare", "clinic"]
        min_class: "C5"
        concern: "hygiene requirements and chemical disinfection"
      - name: "food_processing"
        aliases: ["food", "pharma", "dairy"]
        min_class: "C5"
        concern: "contamination risk and cleaning chemicals"
      - name: "marine"
        aliases: ["coastal", "offshore", "ship"]
        min_class: "C5"
        concern: "salt corrosion"
      - name: "pool"
        aliases: ["swimming", "aquatic"]
        min_class: "C5"
        concern: "chlorine exposure"

clarification_rules:
  required_parameters:
    - name: "capacity"
      aliases: ["airflow", "flow rate", "volume"]
      units: ["m³/h", "cfm", "l/s"]
      prompt: "What is the required {name} ({units[0]})?"
    - name: "dimensions"
      aliases: ["size", "duct size"]
      units: ["mm", "inches"]
      prompt: "What are the duct dimensions (WxH)?"
```

---

### 2. retriever.py - Prompt Examples

**Current:** Lines 1777-1821 have hardcoded GDB examples

**Refactor to:**

```yaml
# domain_config.yaml
prompt_examples:
  variant_selection:
    scenario: "User asks for {family} without specifying {sizing_param}"
    example_variants:
      - name: "{family}-small"
        capacity: 850
      - name: "{family}-medium"
        capacity: 3400
      - name: "{family}-large"
        capacity: 5000
    correct_action: "Return CLARIFICATION_NEEDED, ask for {sizing_param}"
    forbidden_action: "Do not assume a default size"
```

```python
# retriever.py
examples = config.get_prompt_examples()
prompt = PROMPT_TEMPLATE.format(examples=format_examples(examples))
```

---

### 3. config_loader.py - Add Helper Methods

```python
class DomainConfig:
    def get_material_rules_prompt(self) -> str:
        """Generate material/environment rules section for prompts."""
        rules = self.material_environment_rules
        lines = ["**Material class hierarchy:**"]
        for mat in rules['hierarchy']:
            lines.append(f"- {mat['code']} = {mat['class']} ({mat['description']})")

        lines.append("\n**Demanding environments requiring upgraded materials:**")
        for env in rules['environments']['demanding']:
            lines.append(f"- {env['name']}: min {env['min_class']} due to {env['concern']}")

        return "\n".join(lines)

    def get_clarification_rules_prompt(self) -> str:
        """Generate clarification rules section for prompts."""
        rules = self.clarification_rules
        lines = ["**Required parameters for product selection:**"]
        for param in rules['required_parameters']:
            lines.append(f"- {param['name']} ({', '.join(param['units'])})")
        return "\n".join(lines)
```

---

### 4. Frontend - page.tsx Sample Questions

**Current:** Hardcoded GDB/GDC questions

**Refactor to:** Load from API endpoint

```typescript
// page.tsx
const [sampleQuestions, setSampleQuestions] = useState({});

useEffect(() => {
  fetch('/api/config/sample-questions')
    .then(res => res.json())
    .then(data => setSampleQuestions(data));
}, []);
```

```python
# main.py
@app.get("/api/config/sample-questions")
def get_sample_questions():
    config = get_config()
    return config.sample_questions
```

```yaml
# domain_config.yaml
sample_questions:
  housing:
    label: "Housing Selection"
    icon: "🏗️"
    questions:
      - "I need a {product_family} housing for {environment}. {constraint}."
      - "Select a {product_family} for {capacity} {capacity_unit}."

  guardian:
    label: "Guardian Tests"
    icon: "🛡️"
    questions:
      - "I need a cheap housing for pool ventilation in {low_grade_material}."
      - "{product_family} for rooftop installation, no insulation."
```

---

## Implementation Order

1. **Phase 1: Material/Environment Rules** (2-3h)
   - Add `material_environment_rules` to domain_config.yaml
   - Add `get_material_rules_prompt()` to config_loader.py
   - Update chat.py to use dynamic prompt

2. **Phase 2: Sales Assistant Prompt** (2-3h)
   - Move entire SALES_ASSISTANT_SYSTEM_PROMPT to YAML
   - Add template variables for dynamic sections
   - Update chat.py to load from config

3. **Phase 3: Retriever Examples** (1-2h)
   - Add `prompt_examples` to domain_config.yaml
   - Update retriever.py to use config examples

4. **Phase 4: Frontend Sample Questions** (2-3h)
   - Add API endpoint for sample questions
   - Update frontend to load dynamically
   - Remove hardcoded questions from page.tsx

---

## Expected Result

| File | Before | After |
|------|--------|-------|
| chat.py | 29 MH-refs | 0 MH-refs |
| retriever.py | 76 MH-refs | 0 MH-refs |
| prompts.py | 23 MH-refs | 0 MH-refs |
| page.tsx | 50+ MH-refs | 0 MH-refs |
| domain_config.yaml | 435 lines | ~600 lines |

**Total refactoring effort: 8-12 hours**

---

## Benefits

1. **Zero-code domain switching** - Just replace YAML file
2. **Easier maintenance** - Domain experts can edit YAML without coding
3. **Testable configurations** - Validate YAML schema before deployment
4. **Version control** - Track domain changes separately from code changes
5. **Multi-tenant ready** - Load different configs per customer
