# Error Framework Script Examples

These fmxmlsnippet examples preserve the parent/child flow supplied in
`agent/sandbox`:

- [Child script](template-framework-child.xml) validates a JSON payload,
  creates its own error when validation fails, and returns data through
  `Response.Make`.
- [Parent script](template-framework-parent.xml) calls its child with
  `Param.Make`, captures the response immediately with `Response.Capture`, and
  applies logic based on the child's error code.

Each script has one logger call after its main loop, guarded by its error
check. The logger is not called from each error branch. This is one log call
per script; a parent and child can each log their own error once.

These example references are for the VanGenabeek solution: the parent calls
`Playground` with script ID `920`, and the logger is
`(94000) Creeer foutmelding` with script ID `1330`. The logger call runs via
`Perform Script on Server`, passes `Error.Get`, and does not wait for
completion. Rebind both references when using the examples in another solution.
The child returns JSON as example data. Replace that work with the business
operation. After any relevant error-prone FileMaker step, capture the native
error immediately with `FMError.Set` before creating the script's own
application error, as described in
[`agent/docs/knowledge/error-framework.md`](../../../agent/docs/knowledge/error-framework.md).
