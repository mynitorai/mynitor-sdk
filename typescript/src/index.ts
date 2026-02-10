
/**
 * MyNitor AI TypeScript SDK
 * The "One-Line Magic" for AI Production Safety.
 */

// Symbol to prevent double-patching (Idempotency)
const WRAPPED_MARKER = Symbol('mynitor_wrapped');

export interface MyNitorConfig {
    apiKey: string;
    environment?: string;
    endpoint?: string;
    workflowId?: string;
}

export class MyNitor {
    private static instance: MyNitor;
    private config: MyNitorConfig;
    private isInstrumented: boolean = false;
    private pendingPromises: Set<Promise<any>> = new Set();

    private constructor(config: MyNitorConfig) {
        this.config = {
            environment: 'production',
            endpoint: 'https://app.mynitor.ai/api/v1/events',
            ...config
        };

        this.setupAutoFlush();
    }

    private setupAutoFlush(): void {
        const isServerless = !!(
            process.env.AWS_LAMBDA_FUNCTION_NAME ||
            process.env.VERCEL ||
            process.env.NETLIFY ||
            process.env.FUNCTIONS_WORKER_RUNTIME
        );

        if (!isServerless && typeof process !== 'undefined' && typeof process.on === 'function') {
            process.on('beforeExit', async () => {
                await this.flush();
            });
        } else if (isServerless) {
            console.warn('🚀 MyNitor: Serverless environment detected. Ensure you call `await mn.flush()` before your function returns to guarantee log delivery.');
        }
    }

    public static init(config: MyNitorConfig): MyNitor {
        if (!MyNitor.instance) {
            MyNitor.instance = new MyNitor(config);
        } else {
            MyNitor.instance.config = { ...MyNitor.instance.config, ...config };
        }
        return MyNitor.instance;
    }

    /**
     * Automatically detect and wrap AI libraries: OpenAI, Anthropic, and Google Gemini
     */
    public instrument(): void {
        if (this.isInstrumented) return;

        this.wrapOpenAI();
        this.wrapAnthropic();
        this.wrapGemini();

        this.isInstrumented = true;
        console.log('🚀 MyNitor: Universal Auto-instrumentation active.');
    }

    /**
     * Waits for all pending network requests to complete.
     * Call this before your process exits (e.g. in AWS Lambda or scripts).
     * @param timeoutMs Maximum time to wait in milliseconds (default: 10000)
     */
    public async flush(timeoutMs: number = 10000): Promise<void> {
        if (this.pendingPromises.size === 0) return;

        console.log(`🚀 MyNitor: Flushing ${this.pendingPromises.size} pending logs...`);

        const timeoutPromise = new Promise((resolve) => setTimeout(resolve, timeoutMs));
        const allSettledPromise = Promise.allSettled(this.pendingPromises);

        await Promise.race([allSettledPromise, timeoutPromise]);
    }

    private getCallSite() {
        try {
            const err = new Error();
            const stack = err.stack?.split('\n') || [];

            for (const line of stack) {
                // Exclude the SDK's own files, but don't be too broad (e.g. don't skip user's 'mynitor-app')
                const isInternal = line.includes('@mynitorai/sdk') || line.includes('dist/sdk') || line.includes('mynitor/sdk');
                if (!isInternal && !line.includes('Error') && line.includes('/')) {
                    const match = line.match(/at\s+(?:(.+?)\s+\()?(.*?):(\d+):(\d+)\)?/);
                    if (match) {
                        const func = match[1] || 'anonymous';
                        const fullPath = match[2];
                        const filename = fullPath.split('/').pop()?.split('.')[0] || 'unknown';

                        return {
                            file: fullPath,
                            line: parseInt(match[3]),
                            functionName: func,
                            workflowGuess: filename
                        };
                    }
                }
            }
        } catch (e) { }
        return { file: 'unknown', line: 0, functionName: 'unknown', workflowGuess: 'default-workflow' };
    }

    private async sendEvent(payload: any) {
        try {
            const promise = fetch(this.config.endpoint!, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.config.apiKey}`
                },
                body: JSON.stringify({
                    ...payload,
                    environment: this.config.environment,
                    event_version: '1.0',
                    timestamp: new Date().toISOString()
                })
            })
                .then(() => { })
                .catch(() => { })
                .finally(() => {
                    this.pendingPromises.delete(promise);
                });

            this.pendingPromises.add(promise);
        } catch (e) { }
    }

    private wrapOpenAI() {
        try {
            let OpenAI = require('openai');
            if (OpenAI && OpenAI.default) OpenAI = OpenAI.default;
            if (!OpenAI || !OpenAI.OpenAI) return;

            const target = OpenAI.OpenAI.Chat.Completions.prototype;
            if (target[WRAPPED_MARKER]) return;

            const self = this;
            const originalCreate = target.create;

            target.create = async function (this: any, ...args: any[]) {
                const start = Date.now();
                const body = args[0];
                const callsite = self.getCallSite();

                try {
                    const result = await originalCreate.apply(this, args);
                    const end = Date.now();

                    self.sendEvent({
                        request_id: result.id || `req_${Date.now()}`,
                        model: result.model || body.model,
                        provider: 'openai',
                        agent: 'default-agent',
                        workflow: self.config.workflowId || callsite.workflowGuess,
                        file: callsite.file,
                        function_name: callsite.functionName,
                        line_number: callsite.line,
                        input_tokens: result.usage?.prompt_tokens || 0,
                        output_tokens: result.usage?.completion_tokens || 0,
                        latency_ms: end - start,
                        status: 'success'
                    });

                    return result;
                } catch (error: any) {
                    const end = Date.now();
                    self.sendEvent({
                        request_id: `err_${Date.now()}`,
                        model: body?.model || 'unknown',
                        provider: 'openai',
                        agent: 'default-agent',
                        workflow: self.config.workflowId || callsite.workflowGuess,
                        file: callsite.file,
                        function_name: callsite.functionName,
                        latency_ms: end - start,
                        status: 'error',
                        error_type: error?.constructor?.name || 'Error'
                    });
                    throw error;
                }
            };

            target[WRAPPED_MARKER] = true;
        } catch (e) { }
    }

    private wrapAnthropic() {
        try {
            let Anthropic = require('@anthropic-ai/sdk');
            if (Anthropic && Anthropic.default) Anthropic = Anthropic.default;
            if (!Anthropic || !Anthropic.Messages) return;

            const target = Anthropic.Messages.prototype;
            if (target[WRAPPED_MARKER]) return;

            const self = this;
            const originalCreate = target.create;

            target.create = async function (this: any, ...args: any[]) {
                const start = Date.now();
                const body = args[0];
                const callsite = self.getCallSite();

                try {
                    const result = await originalCreate.apply(this, args);
                    const end = Date.now();

                    self.sendEvent({
                        request_id: result.id || `ant_${Date.now()}`,
                        model: result.model || body.model,
                        provider: 'anthropic',
                        agent: 'default-agent',
                        workflow: self.config.workflowId || callsite.workflowGuess,
                        file: callsite.file,
                        function_name: callsite.functionName,
                        line_number: callsite.line,
                        input_tokens: result.usage?.input_tokens || 0,
                        output_tokens: result.usage?.output_tokens || 0,
                        latency_ms: end - start,
                        status: 'success'
                    });

                    return result;
                } catch (error: any) {
                    const end = Date.now();
                    self.sendEvent({
                        request_id: `err_ant_${Date.now()}`,
                        model: body?.model || 'unknown',
                        provider: 'anthropic',
                        agent: 'default-agent',
                        workflow: self.config.workflowId || callsite.workflowGuess,
                        file: callsite.file,
                        function_name: callsite.functionName,
                        latency_ms: end - start,
                        status: 'error',
                        error_type: error?.constructor?.name || 'Error'
                    });
                    throw error;
                }
            };

            target[WRAPPED_MARKER] = true;
        } catch (e) { }
    }

    private wrapGemini() {
        try {
            let GoogleGenAI = require('@google/generative-ai');
            if (GoogleGenAI && GoogleGenAI.default) GoogleGenAI = GoogleGenAI.default;
            if (!GoogleGenAI || !GoogleGenAI.GenerativeModel) return;

            const target = GoogleGenAI.GenerativeModel.prototype;
            if (target[WRAPPED_MARKER]) return;

            const self = this;
            const originalGenerate = target.generateContent;

            target.generateContent = async function (this: any, ...args: any[]) {
                const start = Date.now();
                const callsite = self.getCallSite();

                try {
                    const result = await originalGenerate.apply(this, args);
                    const end = Date.now();
                    const metadata = result.response?.usageMetadata;

                    self.sendEvent({
                        request_id: `gem_${Date.now()}`,
                        model: this.model || 'gemini',
                        provider: 'google',
                        agent: 'default-agent',
                        workflow: self.config.workflowId || callsite.workflowGuess,
                        file: callsite.file,
                        function_name: callsite.functionName,
                        line_number: callsite.line,
                        input_tokens: metadata?.promptTokenCount || 0,
                        output_tokens: metadata?.candidatesTokenCount || 0,
                        latency_ms: end - start,
                        status: 'success'
                    });

                    return result;
                } catch (error: any) {
                    const end = Date.now();
                    self.sendEvent({
                        request_id: `err_gem_${Date.now()}`,
                        model: this.model || 'gemini',
                        provider: 'google',
                        agent: 'default-agent',
                        workflow: self.config.workflowId || callsite.workflowGuess,
                        file: callsite.file,
                        function_name: callsite.functionName,
                        latency_ms: end - start,
                        status: 'error',
                        error_type: error?.constructor?.name || 'Error'
                    });
                    throw error;
                }
            };

            target[WRAPPED_MARKER] = true;
        } catch (e) { }
    }
}

// Global accessor
export const init = MyNitor.init;
