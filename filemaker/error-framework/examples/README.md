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

The parent calls `Playground` with script ID `920`; replace that reference as
needed for the target solution. The logger reference uses ID `0` and the name
`(94000) Creeer foutmelding`; bind it to the target solution's logger. The
child returns JSON as example data. Replace that work with the business
operation. After any relevant error-prone FileMaker step, capture the native
error immediately with `FMError.Set` before creating the script's own
application error, as described in
[`agent/docs/knowledge/error-framework.md`](../../../agent/docs/knowledge/error-framework.md).
