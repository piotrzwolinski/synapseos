#!/usr/bin/env node
/**
 * Wrapper for falkordb-mcpserver that starts the MCP transport FIRST,
 * then connects to FalkorDB in the background. This avoids Claude Code's
 * MCP initialization timeout (the original server blocks ~8s on DB connect
 * before it can respond to the MCP protocol handshake).
 */

const PKG = '/Users/piotrzwolinski/.npm/_npx/b26ea6c539b7b12e/node_modules/falkordb-mcpserver/dist';
const SDK = '/Users/piotrzwolinski/.npm/_npx/b26ea6c539b7b12e/node_modules/@modelcontextprotocol/sdk';

const { McpServer } = await import(`${SDK}/dist/esm/server/mcp.js`);
const { StdioServerTransport } = await import(`${SDK}/dist/esm/server/stdio.js`);

// Import the services from the installed package
const { falkorDBService } = await import(`${PKG}/services/falkordb.service.js`);
const { redisService } = await import(`${PKG}/services/redis.service.js`);
const { logger } = await import(`${PKG}/services/logger.service.js`);
const registerAllTools = (await import(`${PKG}/mcp/tools.js`)).default;
const registerAllResources = (await import(`${PKG}/mcp/resources.js`)).default;
const registerAllPrompts = (await import(`${PKG}/mcp/prompts.js`)).default;

// Create the MCP server
const server = new McpServer({
    name: "falkordb-mcpserver",
    version: "1.0.0"
}, {
    capabilities: {
        tools: { listChanged: true },
        resources: { listChanged: true },
        prompts: { listChanged: true },
        logging: {},
    }
});

logger.setMcpServer(server);
registerAllTools(server);
registerAllResources(server);
registerAllPrompts(server);

// Start the transport IMMEDIATELY (so Claude Code gets the handshake)
const transport = new StdioServerTransport();
await server.connect(transport);

// THEN connect to FalkorDB in the background
try {
    await falkorDBService.initialize();
    await redisService.initialize();
    await logger.info('All services initialized successfully');
} catch (error) {
    await logger.error('Failed to initialize services', error instanceof Error ? error : new Error(String(error)));
}

// Graceful shutdown
const gracefulShutdown = async (signal) => {
    await logger.info(`Received ${signal}, shutting down gracefully`);
    try {
        await falkorDBService.close();
        await redisService.close();
        process.exit(0);
    } catch (error) {
        process.exit(1);
    }
};
process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
process.on('SIGINT', () => gracefulShutdown('SIGINT'));
