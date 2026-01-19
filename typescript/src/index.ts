
/**
 * MyNitor AI TypeScript SDK
 * The "One-Line Magic" for AI Production Safety.
 */

export interface MyNitorConfig {
    apiKey: string;
    environment?: string;
    endpoint?: string;
}

export class MyNitor {
    private static instance: MyNitor;
    private config: MyNitorConfig;
    private isInstrumented: boolean = false;

    private constructor(config: MyNitorConfig) {
        this.config = {
            environment: 'production',
            endpoint: 'https://app.mynitor.ai/api/v1/events',
            ...config
        };
    }

    public static init(config: MyNitorConfig): MyNitor {
        if (!MyNitor.instance) {
            MyNitor.instance = new MyNitor(config);
        }
        return MyNitor.instance;
    }

    /**
     * Automatically detect and wrap AI libraries like OpenAI
     */
    public instrument(): void {
        if (this.isInstrumented) return;

        this.wrapOpenAI();
        this.isInstrumented = true;
        console.log('🚀 MyNitor: Auto-instrumentation active.');
    }

    private async sendEvent(payload: any) {
        try {
            // Fire and forget - we don't await this to keep the user's app fast
            fetch(this.config.endpoint!, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.config.apiKey}`
                },
                body: JSON.stringify({
                    ...payload,
                    environment: this.config.environment,
                    eventVersion: '1.0'
                })
            }).catch(() => {
                /* Silently fail to protect the user's production app */
            });
        } catch (e) {
            /* Silently fail */
        }
    }

    private wrapOpenAI() {
        try {
            // Detect if OpenAI is installed
            const OpenAI = require('openai');
            if (!OpenAI || !OpenAI.OpenAI) return;

            const self = this;
            const originalChatCreate = OpenAI.OpenAI.Chat.Completions.prototype.create;

            OpenAI.OpenAI.Chat.Completions.prototype.create = async function (this: any, ...args: any[]) {
                const start = Date.now();
                const body = args[0];

                try {
                    const result = await originalChatCreate.apply(this, args);
                    const end = Date.now();

                    // Background capture
                    self.sendEvent({
                        requestId: result.id || `req_${Date.now()}`,
                        model: result.model || body.model,
                        provider: 'openai',
                        inputTokens: result.usage?.prompt_tokens || 0,
                        outputTokens: result.usage?.completion_tokens || 0,
                        latencyMs: end - start,
                        status: 'success'
                    });

                    return result;
                } catch (error: any) {
                    const end = Date.now();

                    self.sendEvent({
                        requestId: `err_${Date.now()}`,
                        model: body?.model || 'unknown',
                        provider: 'openai',
                        inputTokens: 0,
                        outputTokens: 0,
                        latencyMs: end - start,
                        status: 'error',
                        errorType: error?.constructor?.name || 'Error'
                    });

                    throw error;
                }
            };
        } catch (e) {
            // Library not found or version mismatch - skip silently
        }
    }
}

// Global accessor for snippet simplicity
export const init = MyNitor.init;
