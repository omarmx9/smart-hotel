/**
 * Node-RED Settings - Headless Notification Gateway Configuration
 * 
 * This configuration runs Node-RED in headless mode (no editor UI)
 * and exposes HTTP API endpoints and MQTT integration for notifications.
 * Supports Telegram and SMS (Twilio) with automatic fallback.
 */

module.exports = {
    // Disable the editor UI completely for headless operation
    httpAdminRoot: false,
    
    // Enable HTTP endpoints for flows
    httpNodeRoot: '/api',
    
    // Flow file location
    flowFile: 'flows.json',
    
    // Credential encryption key from environment
    credentialSecret: process.env.NODE_RED_CREDENTIAL_SECRET || false,
    
    // Logging configuration
    logging: {
        console: {
            level: process.env.NODE_RED_LOG_LEVEL || "info",
            metrics: false,
            audit: false
        }
    },
    
    // Disable projects since we're running headless
    editorTheme: {
        projects: {
            enabled: false
        }
    },
    
    // Function global context - make environment variables available to flows
    functionGlobalContext: {
        // Telegram Bot Configuration
        TELEGRAM_BOT_TOKEN: process.env.TELEGRAM_BOT_TOKEN,
        TELEGRAM_CHAT_ID: process.env.TELEGRAM_CHAT_ID,
        
        // Twilio SMS Configuration
        TWILIO_ACCOUNT_SID: process.env.TWILIO_ACCOUNT_SID,
        TWILIO_AUTH_TOKEN: process.env.TWILIO_AUTH_TOKEN,
        TWILIO_PHONE_NUMBER: process.env.TWILIO_PHONE_NUMBER,
        
        // MQTT Configuration (for broker authentication)
        MQTT_USER: process.env.MQTT_USER,
        MQTT_PASSWORD: process.env.MQTT_PASSWORD
    },
    
    // Disable externalModules installation in runtime
    externalModules: {
        autoInstall: false,
        autoInstallRetry: 0,
        palette: {
            allowInstall: false,
            allowUpload: false,
            allowList: [],
            denyList: []
        },
        modules: {
            allowInstall: false,
            allowList: [],
            denyList: []
        }
    }
};
