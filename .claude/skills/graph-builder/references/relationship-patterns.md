# Relationship Patterns — Complete Catalog

## Layer 1: Inventory

```
(:ProductFamily)-[:HAS_TRAIT]->(:PhysicalTrait)           # Product capabilities
(:ProductFamily)-[:AVAILABLE_IN_MATERIAL]->(:Material)     # Available materials
(:ProductFamily)-[:AVAILABLE_IN_SIZE]->(:DimensionModule)  # Available dimensions
(:ProductFamily)-[:HAS_CAPACITY]->(:CapacityRule)          # Throughput limits
(:ProductFamily)-[:HAS_LENGTH_VARIANT]->(:VariantLength)   # Housing length options
(:ProductFamily)-[:HAS_VARIABLE_FEATURE]->(:VariableFeature)  # User-selectable features
(:ProductFamily)-[:HAS_OPTION]->(:Option)                  # Standard options
(:ProductFamily)-[:HAS_DEFAULT_OPTION]->(:Option)          # Default option set
(:ProductFamily)-[:INCLUDES_FEATURE]->(:Feature)           # Built-in features
(:ProductFamily)-[:HAS_COMPATIBLE_ACCESSORY]->(:Accessory) # Compatible accessories
(:ProductFamily)-[:INCOMPATIBLE_WITH]->(:Accessory)        # Incompatible accessories
(:ProductFamily)-[:SUGGESTS_CROSS_SELL]->(:Accessory|Consumable|Option|Solution)  # Upsell
(:ProductFamily)-[:USES_MOUNTING_SYSTEM]->(:MountingSystem)
(:ProductFamily)-[:SUITABLE_FOR]->(:Environment)           # Explicit suitability

(:Material)-[:PROVIDES_TRAIT]->(:PhysicalTrait)            # Material capabilities
(:Material)-[:COMPLIES_WITH]->(:Regulation)
(:Material)-[:MEETS_REQUIREMENT]->(:Requirement)
(:Material)-[:VULNERABLE_TO]->(:Risk)

(:VariableFeature)-[:HAS_OPTION]->(:FeatureOption)
(:VariableFeature)-[:SELECTION_DEPENDS_ON]->(:Discriminator)

(:ProductVariant)-[:FROM_DOCUMENT]->(:DocumentSource)
(:ProductVariant)-[:IS_CATEGORY]->(:Category)
(:ProductVariant)-[:ACCEPTS_FILTER]->(:FilterConsumable)
(:ProductVariant)-[:COMPATIBLE_WITH_DUCT]->(:DuctConnection)
```

## Layer 2: Physics / Domain Rules

```
(:Application)-[:EXPOSES_TO]->(:EnvironmentalStressor)     # What stressors an app creates
(:Application)-[:GENERATES]->(:Substance)                  # What substances it produces
(:Application)-[:HAS_RISK]->(:Risk)                        # Known risks
(:Application)-[:TRIGGERS_GATE]->(:LogicGate)              # Gates it activates
(:Application)-[:MAY_BE_ENVIRONMENT]->(:Environment)       # Associated environment
(:Application)-[:REQUIRES_COMPLIANCE]->(:Regulation)
(:Application)-[:REQUIRES_RESISTANCE]->(:Requirement)

(:Environment)-[:EXPOSES_TO]->(:EnvironmentalStressor)     # Environmental stressors
(:Environment)-[:CAUSES]->(:Risk)
(:Environment)-[:GENERATES]->(:Substance)
(:Environment)-[:HAS_RISK]->(:Risk)
(:Environment)-[:TRIGGERS_GATE]->(:LogicGate)
(:Environment)-[:IS_A]->(:Environment)                     # Hierarchy (ENV_KITCHEN IS_A ENV_INDOOR)

(:EnvironmentalStressor)-[:DEMANDS_TRAIT]->(:PhysicalTrait) # THE core physics rule
(:PhysicalTrait)-[:NEUTRALIZED_BY]->(:EnvironmentalStressor)  # Reverse: trait killed by stressor

(:DependencyRule)-[:TRIGGERED_BY_STRESSOR]->(:EnvironmentalStressor)
(:DependencyRule)-[:UPSTREAM_REQUIRES_TRAIT]->(:PhysicalTrait)   # Protector must have this
(:DependencyRule)-[:DOWNSTREAM_PROVIDES_TRAIT]->(:PhysicalTrait) # Target has this

(:ProductFamily)-[:VULNERABLE_TO]->(:Risk)                 # Product weaknesses
(:ProductFamily)-[:VULNERABLE_TO]->(:Substance)
(:ProductFamily)-[:PRONE_TO]->(:Risk)
(:ProductFamily)-[:PROTECTS_AGAINST]->(:Risk)
(:ProductFamily)-[:INEFFECTIVE_AGAINST]->(:Substance)

(:Substance)-[:CAUSES]->(:Risk)
(:Risk)-[:MITIGATED_BY]->(:Feature|Solution)
(:Risk)-[:TRIGGERS_STRATEGY]->(:Strategy)
```

## Layer 3: Playbook / Decision Logic

```
(:LogicGate)-[:MONITORS]->(:EnvironmentalStressor)         # What stressor triggers gate
(:LogicGate)-[:REQUIRES_DATA]->(:Parameter)                # What data needed to evaluate

(:Parameter)-[:ASKED_VIA]->(:Question)                     # How to ask user

(:ProductFamily)-[:HAS_HARD_CONSTRAINT]->(:HardConstraint)  # Hard limits
(:ProductFamily)-[:HAS_INSTALLATION_CONSTRAINT]->(:InstallationConstraint)
(:ProductFamily)-[:HAS_SIZING_RULE]->(:SizingRule)
(:ProductFamily)-[:OPTIMIZATION_STRATEGY]->(:Strategy)
(:ProductFamily)-[:REQUIRES_PARAMETER]->(:Parameter)       # What params needed

(:ClarificationRule)-[:APPLIES_TO_PRODUCT]->(:ProductFamily)
(:ClarificationRule)-[:DEMANDS_PARAMETER]->(:Parameter)
(:ClarificationRule)-[:TRIGGERED_BY_CONTEXT]->(:Application)

(:FunctionalGoal)-[:REQUIRES_TRAIT]->(:PhysicalTrait)
```

## Layer 4: Session State (Runtime Only)

```
(:Session)-[:WORKING_ON]->(:ActiveProject)
(:ActiveProject)-[:HAS_UNIT]->(:TagUnit)
(:ActiveProject)-[:TARGETS_FAMILY]->(:ProductFamily)
(:ActiveProject)-[:USES_MATERIAL]->(:Material)
(:ActiveProject)-[:HAS_TURN]->(:ConversationTurn)
(:TagUnit)-[:SIZED_AS]->(:DimensionModule)
```

## Key Traversal Patterns Used by Engine

### Stressor Detection (Full Chain)
```
(:Application)-[:EXPOSES_TO]->(:EnvironmentalStressor)-[:DEMANDS_TRAIT]->(:PhysicalTrait)
```

### Assembly Decision
```
(:EnvironmentalStressor)-[:DEMANDS_TRAIT]->(:PhysicalTrait)  -- product lacks this trait
(:DependencyRule)-[:TRIGGERED_BY_STRESSOR]->(:EnvironmentalStressor)  -- find protector rule
(:DependencyRule)-[:UPSTREAM_REQUIRES_TRAIT]->(:PhysicalTrait)  -- protector needs this trait
(:ProductFamily)-[:HAS_TRAIT]->(:PhysicalTrait)  -- find product with that trait
```

### Gate Evaluation
```
(:Application|Environment)-[:TRIGGERS_GATE]->(:LogicGate)-[:REQUIRES_DATA]->(:Parameter)
```

### Installation Constraint Check
```
(:ProductFamily)-[:HAS_INSTALLATION_CONSTRAINT]->(:InstallationConstraint)
(:ProductFamily)-[:AVAILABLE_IN_MATERIAL]->(:Material)  -- for CROSS_NODE_THRESHOLD
```

### Capacity + Sizing
```
(:ProductFamily)-[:HAS_CAPACITY]->(:CapacityRule)
(:ProductFamily)-[:AVAILABLE_IN_SIZE]->(:DimensionModule)
(:DimensionModule)-[:DETERMINES_PROPERTY]->(:SizeProperty)  -- family-specific component count
```
