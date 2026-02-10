import os
import time
import uuid
import requests
import logging
import inspect
import hashlib
import atexit
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger("mynitor")

class Mynitor:
    def __init__(self, api_key=None, api_url=None, workflow_id=None):
        self.api_key = api_key or os.getenv("MYNITOR_API_KEY")
        self.api_url = api_url or os.getenv("MYNITOR_API_URL", "https://app.mynitor.ai/api/v1/events")
        self.workflow_id = workflow_id
        self._executor = ThreadPoolExecutor(max_workers=5)
        self._setup_auto_flush()

    def _setup_auto_flush(self):
        is_serverless = any(os.getenv(k) for k in [
            "AWS_LAMBDA_FUNCTION_NAME", 
            "VERCEL", 
            "NETLIFY", 
            "FUNCTIONS_WORKER_RUNTIME"
        ])
        
        if not is_serverless:
            atexit.register(self.flush)
        else:
            logger.info("🚀 MyNitor: Serverless environment detected. Ensure you call `mn.flush()` before your function returns.")

    def flush(self, timeout=10):
        """
        Waits for all pending network requests to complete.
        Call this before your function returns in serverless environments.
        """
        if self._executor:
            self._executor.shutdown(wait=True)
            # Re-create executor in case the instance is reused
            self._executor = ThreadPoolExecutor(max_workers=5)

    def _get_callsite(self):
        """
        Captures the file, line number, and function name of the caller.
        """
        try:
            stack = inspect.stack()
            this_file = os.path.abspath(__file__)
            
            for frame in stack:
                # Skip frames inside the mynitor package
                if os.path.abspath(frame.filename) == this_file:
                    continue
                
                # Skip internal python contextlib frames
                if "contextlib.py" in frame.filename:
                    continue
                
                filename = frame.filename
                try:
                    rel_path = os.path.relpath(filename, os.getcwd())
                except Exception:
                    rel_path = filename
                
                function = frame.function
                lineno = frame.lineno
                
                # Generate a unique hash for this callsite
                callsite_id = f"{rel_path}:{lineno}:{function}"
                callsite_hash = hashlib.md5(callsite_id.encode()).hexdigest()[:8]
                
                return {
                    "file": rel_path,
                    "line_number": lineno,
                    "function_name": function,
                    "callsite_hash": callsite_hash
                }
        except Exception:
            pass
        return {}

    def _derive_workflow_name(self, callsite):
        """
        Smart Naming: generic "default-workflow" is redundant.
        We should use the file:function as the default workflow name.
        """
        try:
            filename = os.path.basename(callsite.get("file", "unknown"))
            # remove extension
            if "." in filename:
                filename = filename.rsplit(".", 1)[0]
            
            func = callsite.get("function_name", "unknown")
            return filename
        except Exception:
            return "default-workflow"

    @contextmanager
    def monitor(self, agent: str, workflow: str = None, model: str = None, provider: str = "other"):
        """
        Context manager to track LLM calls.
        Usage:
            with mn.monitor(agent="bot", workflow="chat", model="gpt-4") as tracker:
                # ... call LLM ...
        """
        start_time = time.time()
        request_id = str(uuid.uuid4())
        callsite = self._get_callsite()
        
        # Smart Naming
        if not workflow:
            workflow = self.workflow_id or self._derive_workflow_name(callsite)

        # Internal state to capture usage
        state = {
            "input_tokens": 0,
            "output_tokens": 0,
            "retry_count": 0,
            "status": "success",
            "error_type": None,
            "metadata": {}
        }

        class Tracker:
            def set_usage(self, input_tokens: int, output_tokens: int):
                state["input_tokens"] = input_tokens
                state["output_tokens"] = output_tokens
            
            def set_retry(self, count: int):
                state["retry_count"] = count
                
            def set_metadata(self, key: str, value: any):
                state["metadata"][key] = value

        tracker = Tracker()

        try:
            yield tracker
        except Exception as e:
            state["status"] = "error"
            state["error_type"] = type(e).__name__
            state["metadata"]["error_message"] = str(e)
            raise e
        finally:
            latency = int((time.time() - start_time) * 1000)
            
            # FAIL-SAFE: Never crash the host app for telemetry
            try:
                self._send_event(
                    agent=agent,
                    workflow=workflow,
                    model=model,
                    provider=provider,
                    request_id=request_id,
                    latency_ms=latency,
                    **callsite,
                    **state
                )
            except Exception as e:
                logger.warning(f"Mynitor Telemetry Failed: {e}")

    def instrument_openai(self, client, agent: str = "default-agent", workflow: str = None):
        """
        Wraps an OpenAI client (or OpenAI-compatible client like DeepSeek/Groq) 
        to automatically track usage.
        """
        original_create = client.chat.completions.create
        
        # Idempotency Check
        if getattr(original_create, "_is_mynitor_wrapped", False):
            return client

        def patched_create(*args, **kwargs):
            model = kwargs.get("model", "unknown")
            start_time = time.time()
            request_id = str(uuid.uuid4())
            callsite = self._get_callsite()

            # Smart Naming
            current_workflow = workflow
            if not current_workflow:
                current_workflow = self.workflow_id or self._derive_workflow_name(callsite)
            
            try:
                response = original_create(*args, **kwargs)
                
                # Capture usage data automatically
                usage = getattr(response, 'usage', None)
                input_tokens = getattr(usage, 'prompt_tokens', 0) if usage else 0
                output_tokens = getattr(usage, 'completion_tokens', 0) if usage else 0
                
                latency = int((time.time() - start_time) * 1000)
                
                self._send_event(
                    agent=agent,
                    workflow=current_workflow,
                    model=model,
                    provider="openai",
                    request_id=request_id,
                    latency_ms=latency,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    status="success",
                    **callsite
                )
                return response
            except Exception as e:
                self._handle_exception(e, agent, current_workflow, model, "openai", request_id, start_time, callsite)
                raise e

        client.chat.completions.create = patched_create
        setattr(patched_create, "_is_mynitor_wrapped", True)
        return client

    def instrument_anthropic(self, client, agent: str = "default-agent", workflow: str = None):
        """
        Wraps an Anthropic client (Sync or Async) to automatically track usage.
        """
        # Detect if this is an AsyncAnthropic client
        is_async = hasattr(client, '__aenter__') or 'Async' in type(client).__name__
        original_create = client.messages.create

        # Idempotency Check
        if getattr(original_create, "_is_mynitor_wrapped", False):
            return client

        if is_async:
            async def patched_create(*args, **kwargs):
                model = kwargs.get("model", "unknown")
                start_time = time.time()
                callsite = self._get_callsite()
                current_workflow = workflow or self.workflow_id or self._derive_workflow_name(callsite)

                try:
                    response = await original_create(*args, **kwargs)
                    usage = getattr(response, 'usage', None)
                    latency = int((time.time() - start_time) * 1000)
                    
                    self._send_event(
                        agent=agent,
                        workflow=current_workflow,
                        model=getattr(response, 'model', model),
                        provider="anthropic",
                        request_id=getattr(response, 'id', str(uuid.uuid4())),
                        latency_ms=latency,
                        input_tokens=getattr(usage, 'input_tokens', 0) if usage else 0,
                        output_tokens=getattr(usage, 'output_tokens', 0) if usage else 0,
                        status="success",
                        **callsite
                    )
                    return response
                except Exception as e:
                    self._handle_exception(e, agent, current_workflow, model, "anthropic", str(uuid.uuid4()), start_time, callsite)
                    raise e
        else:
            def patched_create(*args, **kwargs):
                model = kwargs.get("model", "unknown")
                start_time = time.time()
                callsite = self._get_callsite()
                current_workflow = workflow or self.workflow_id or self._derive_workflow_name(callsite)

                try:
                    response = original_create(*args, **kwargs)
                    usage = getattr(response, 'usage', None)
                    latency = int((time.time() - start_time) * 1000)
                    
                    self._send_event(
                        agent=agent,
                        workflow=current_workflow,
                        model=getattr(response, 'model', model),
                        provider="anthropic",
                        request_id=getattr(response, 'id', str(uuid.uuid4())),
                        latency_ms=latency,
                        input_tokens=getattr(usage, 'input_tokens', 0) if usage else 0,
                        output_tokens=getattr(usage, 'output_tokens', 0) if usage else 0,
                        status="success",
                        **callsite
                    )
                    return response
                except Exception as e:
                    self._handle_exception(e, agent, current_workflow, model, "anthropic", str(uuid.uuid4()), start_time, callsite)
                    raise e

        client.messages.create = patched_create
        setattr(patched_create, "_is_mynitor_wrapped", True)
        return client

    def instrument_gemini(self, model_instance, agent: str = "default-agent", workflow: str = None):
        """
        Wraps a Google GenerativeAI (Gemini) model instance (Sync or Async) to automatically track usage.
        """
        # Patch both sync and async methods if they exist
        methods_to_patch = [
            ("generate_content", False),
            ("generate_content_async", True)
        ]

        for method_name, is_async in methods_to_patch:
            if not hasattr(model_instance, method_name):
                continue
            
            original_method = getattr(model_instance, method_name)
            if getattr(original_method, "_is_mynitor_wrapped", False):
                continue

            if is_async:
                async def patched_method(*args, **kwargs):
                    model_name = getattr(model_instance, 'model_name', "gemini-unknown")
                    start_time = time.time()
                    request_id = str(uuid.uuid4())
                    callsite = self._get_callsite()
                    current_workflow = workflow or self.workflow_id or self._derive_workflow_name(callsite)

                    try:
                        response = await original_method(*args, **kwargs)
                        usage = getattr(response, 'usage_metadata', None)
                        latency = int((time.time() - start_time) * 1000)
                        
                        self._send_event(
                            agent=agent,
                            workflow=current_workflow,
                            model=model_name,
                            provider="google",
                            request_id=request_id,
                            latency_ms=latency,
                            input_tokens=getattr(usage, 'prompt_token_count', 0) if usage else 0,
                            output_tokens=getattr(usage, 'candidates_token_count', 0) if usage else 0,
                            status="success",
                            **callsite
                        )
                        return response
                    except Exception as e:
                        self._handle_exception(e, agent, current_workflow, model_name, "google", request_id, start_time, callsite)
                        raise e
            else:
                def patched_method(*args, **kwargs):
                    model_name = getattr(model_instance, 'model_name', "gemini-unknown")
                    start_time = time.time()
                    request_id = str(uuid.uuid4())
                    callsite = self._get_callsite()
                    current_workflow = workflow or self.workflow_id or self._derive_workflow_name(callsite)

                    try:
                        response = original_method(*args, **kwargs)
                        usage = getattr(response, 'usage_metadata', None)
                        latency = int((time.time() - start_time) * 1000)
                        
                        self._send_event(
                            agent=agent,
                            workflow=current_workflow,
                            model=model_name,
                            provider="google",
                            request_id=request_id,
                            latency_ms=latency,
                            input_tokens=getattr(usage, 'prompt_token_count', 0) if usage else 0,
                            output_tokens=getattr(usage, 'candidates_token_count', 0) if usage else 0,
                            status="success",
                            **callsite
                        )
                        return response
                    except Exception as e:
                        self._handle_exception(e, agent, current_workflow, model_name, "google", request_id, start_time, callsite)
                        raise e

            setattr(model_instance, method_name, patched_method)
            setattr(patched_method, "_is_mynitor_wrapped", True)

        return model_instance

    def _handle_exception(self, e, agent, workflow, model, provider, request_id, start_time, callsite=None):
        latency = int((time.time() - start_time) * 1000)
        callsite = callsite or {}
        try:
            self._send_event(
                agent=agent,
                workflow=workflow,
                model=model,
                provider=provider,
                request_id=request_id,
                latency_ms=latency,
                status="error",
                error_type=type(e).__name__,
                metadata={"error_message": str(e)},
                **callsite
            )
        except Exception:
            pass

    def _send_event(self, **kwargs):
        if not self._executor:
             return

        payload = {
            "event_version": "1.0",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            **kwargs
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Dispatch to background thread
        try:
            self._executor.submit(self._do_send_request, payload, headers)
        except Exception:
            pass

    def _do_send_request(self, payload, headers):
        try:
            requests.post(self.api_url, json=payload, headers=headers, timeout=5)
        except Exception:
            pass # Fail-safe

# Global Instance for Magic Initialization
_instance = None

def init(api_key=None):
    global _instance
    _instance = Mynitor(api_key=api_key)
    return _instance

def instrument(agent: str = "default-agent"):
    if not _instance:
        logger.warning("Mynitor.init() must be called before instrument()")
        return
    
    # 1. Automatic OpenAI Patching
    try:
        import openai
        if hasattr(openai, 'OpenAI'):
            _instance.instrument_openai(openai.OpenAI, agent=agent)
        if hasattr(openai, 'AsyncOpenAI'):
            _instance.instrument_openai(openai.AsyncOpenAI, agent=agent)
    except ImportError:
        pass
    
    # 2. Automatic Anthropic Patching
    try:
        import anthropic
        if hasattr(anthropic, 'Anthropic'):
            _instance.instrument_anthropic(anthropic.Anthropic, agent=agent)
        if hasattr(anthropic, 'AsyncAnthropic'):
            _instance.instrument_anthropic(anthropic.AsyncAnthropic, agent=agent)
    except ImportError:
        pass

    # 3. Automatic Gemini Patching
    try:
        import google.generativeai as genai
        if hasattr(genai, 'GenerativeModel'):
            _instance.instrument_gemini(genai.GenerativeModel, agent=agent)
    except ImportError:
        pass
    
    logger.info("🚀 MyNitor: Universal Auto-instrumentation active.")
