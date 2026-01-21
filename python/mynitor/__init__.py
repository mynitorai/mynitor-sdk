import os
import time
import uuid
import requests
import logging
import inspect
import hashlib
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger("mynitor")

class Mynitor:
    def __init__(self, api_key=None, api_url=None):
        self.api_key = api_key or os.getenv("MYNITOR_API_KEY")
        self.api_url = api_url or os.getenv("MYNITOR_API_URL", "https://devmynitorai.netlify.app/api/v1/events")

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
            return f"{filename}:{func}"
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
            workflow = self._derive_workflow_name(callsite)

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

        def patched_create(*args, **kwargs):
            model = kwargs.get("model", "unknown")
            start_time = time.time()
            request_id = str(uuid.uuid4())
            callsite = self._get_callsite()

            # Smart Naming
            current_workflow = workflow
            if not current_workflow:
                current_workflow = self._derive_workflow_name(callsite)
            
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
        return client

    def instrument_anthropic(self, client, agent: str = "default-agent", workflow: str = None):
        """
        Wraps an Anthropic client to automatically track usage.
        """
        original_create = client.messages.create

        def patched_create(*args, **kwargs):
            model = kwargs.get("model", "unknown")
            start_time = time.time()
            request_id = str(uuid.uuid4())
            callsite = self._get_callsite()
            
            # Smart Naming
            current_workflow = workflow
            if not current_workflow:
                current_workflow = self._derive_workflow_name(callsite)

            try:
                response = original_create(*args, **kwargs)
                
                usage = getattr(response, 'usage', None)
                input_tokens = getattr(usage, 'input_tokens', 0) if usage else 0
                output_tokens = getattr(usage, 'output_tokens', 0) if usage else 0
                
                latency = int((time.time() - start_time) * 1000)
                
                self._send_event(
                    agent=agent,
                    workflow=current_workflow,
                    model=model,
                    provider="anthropic",
                    request_id=request_id,
                    latency_ms=latency,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    status="success",
                    **callsite
                )
                return response
            except Exception as e:
                self._handle_exception(e, agent, current_workflow, model, "anthropic", request_id, start_time, callsite)
                raise e

        client.messages.create = patched_create
        return client

    def instrument_gemini(self, model_instance, agent: str = "default-agent", workflow: str = None):
        """
        Wraps a Google GenerativeAI (Gemini) model instance to automatically track usage.
        """
        original_generate = model_instance.generate_content

        def patched_generate(*args, **kwargs):
            model_name = getattr(model_instance, 'model_name', "gemini-unknown")
            start_time = time.time()
            request_id = str(uuid.uuid4())
            callsite = self._get_callsite()
            
            # Smart Naming
            current_workflow = workflow
            if not current_workflow:
                current_workflow = self._derive_workflow_name(callsite)

            try:
                response = original_generate(*args, **kwargs)
                
                usage = getattr(response, 'usage_metadata', None)
                input_tokens = getattr(usage, 'prompt_token_count', 0) if usage else 0
                output_tokens = getattr(usage, 'candidates_token_count', 0) if usage else 0
                
                latency = int((time.time() - start_time) * 1000)
                
                self._send_event(
                    agent=agent,
                    workflow=current_workflow,
                    model=model_name,
                    provider="google",
                    request_id=request_id,
                    latency_ms=latency,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    status="success",
                    **callsite
                )
                return response
            except Exception as e:
                self._handle_exception(e, agent, current_workflow, model_name, "google", request_id, start_time, callsite)
                raise e

        model_instance.generate_content = patched_generate
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
        payload = {
            "event_version": "1.0",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            **kwargs
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Fire and forget / simple POST
        try:
            requests.post(self.api_url, json=payload, headers=headers, timeout=2)
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
        # Try Patching the Global OpenAI Sync Client and Async Client
        if hasattr(openai, 'OpenAI'):
            _instance.instrument_openai(openai.OpenAI, agent=agent)
        if hasattr(openai, 'AsyncOpenAI'):
            _instance.instrument_openai(openai.AsyncOpenAI, agent=agent)
    except ImportError:
        pass
    
    # 2. Add other libraries as needed (Anthropic, etc.)
    
    print("🚀 MyNitor: Auto-instrumentation active.")
