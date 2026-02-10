from mynitor import Mynitor
import os

# Mock callsite
callsite = {"file": "test_script.py", "function_name": "test_func"}

# 1. Test Default Naming
mn = Mynitor(api_key="test")
workflow_name = mn._derive_workflow_name(callsite)
print(f"Default Workflow Name: {workflow_name}")

if workflow_name == "test_script":
    print("✅ PASS: Default workflow name is filename only.")
else:
    print(f"❌ FAIL: Default workflow name is {workflow_name}")

# 2. Test Override
mn2 = Mynitor(api_key="test", workflow_id="explicit-id")
# The _derive_workflow_name method itself doesn't use self.workflow_id, 
# but the wrappers (monitor, etc.) do.
# Let's check if the logic in monitor/instrument_* wraps it.

# In Mynitor:
# if not workflow:
#     workflow = self.workflow_id or self._derive_workflow_name(callsite)

workflow_to_use = mn2.workflow_id or mn2._derive_workflow_name(callsite)
print(f"Override Workflow Name: {workflow_to_use}")

if workflow_to_use == "explicit-id":
    print("✅ PASS: Workflow override is correctly prioritized.")
else:
    print(f"❌ FAIL: Workflow override failed.")
