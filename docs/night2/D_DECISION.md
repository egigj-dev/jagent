<!-- Workflow decision; existing functions and the explicit offline CLI provide stage separation. -->
# D decision

Existing pipeline stages suffice. The preview explicitly composes assessment,
serialized restore, ranking and mentor functions. It needs neither background
execution nor retries: all stages are local deterministic computations. Cache
restore is an idempotent evidence boundary, not a workflow engine. No LangGraph,
new dependency, scheduler, autonomous agent or checkpoint service was installed.
