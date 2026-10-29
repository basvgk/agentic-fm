# Record Locking in Multi-User Environments

## Project error-framework override

Use this article for locking semantics, retry decisions, and transaction
guidance. The step-to-error table and immediate capture rules are centralized
in [`error-framework.md`](error-framework.md); use that document for every
script change when the project framework is active. This article does not
define a separate error-capture pattern.

**NOTE:** Items marked with **(step)** are script steps. Items marked with **(function)** are calculation functions used inside expressions.

## The Locking Model

FileMaker uses **optimistic record-level locking**. A record exists in one of two states:

- **Committed** — not being edited, no write lock, any client can read it.
- **Open (in edit mode)** — a client holds the write lock. No other client can open the same record for editing until the lock is released.

A record enters edit mode when:

- A user clicks into a field on a layout **and modifies the field contents**
- A script executes `Open Record/Request` **(step)**
- A script executes `Set Field` **(step)** (implicitly opens the record)
- A script executes an `Insert` step that modifies field data
- A portal row is modified

The write lock is released when:

- A script executes `Commit Records/Requests` **(step)**
- A script executes `Revert Record/Request` **(step)**
- The open record is navigated off of (e.g. previous/next buttons, entering Find mode, or any action that leaves the record)
- The user's session disconnects

## The Error Codes

| Code | Meaning                                 | Context                                                                   |
| ---- | --------------------------------------- | ------------------------------------------------------------------------- |
| 301  | Record is in use by another user        | `Open Record/Request`, `Set Field` on a locked record                     |
| 306  | Record modification ID does not match   | Record was modified by another process between open and commit            |
| 307  | Transaction could not be locked (comms) | Communication error with host while acquiring a transaction lock          |
| 512  | Record was already modified by another user | Concurrent modification of a record                                      |

Error 301 means another client holds the write lock. Error 306 means the
record's modification ID changed between opening and committing. Error 307
means a communication error prevented a transaction lock. Error 512 also
indicates that another user modified the record.

## The Silent Failure Problem

When `Set Error Capture [ On ]` suppresses dialogs, a failed write may not
show a native dialog. If the script continues without handling the failure,
later steps can proceed as though the write succeeded. This is particularly
dangerous for financial transactions, inventory adjustments, and status changes
that trigger downstream processes. Capture placement is defined in
`error-framework.md`.

`Set Field` **(step)** implicitly opens the record if it is not already open.
If another client holds the lock, the write can fail with error 301. A
related-table `Set Field` (`Set Field [ relatedTable::field ; value ]`) can
also fail this way if the related record is locked. Use the capture timing in
`error-framework.md` for both cases.

## Checking before a sequence of field changes

When a script will modify the current record, prefer `Open Record/Request`
**(step)** before the write sequence and check it immediately. If it succeeds,
the record is open for editing. If the script does not explicitly open it, the
first `Set Field` opens it implicitly and is the point to check for a lock
failure.

After that successful lock acquisition, additional `Set Field` steps on the
same record do not need repeated checks solely to detect the same lock. Check
every `Set Field` when field-level privileges, access rules, or another
field-specific failure is relevant. A `Set Field` that modifies a related
record needs its own check. Check `Commit Records/Requests` after the write
sequence for commit, validation, and concurrent-modification failures.

## Record Modification Count

If a `Set Field` succeeds and the record is subsequently committed, the record's internal modification counter increments. `Get ( RecordModificationCount )` **(function)** can be compared before and after a sequence of operations to determine whether the record was actually modified. This is useful as a secondary verification that a commit changed data.

## Retry Logic for Transient Locks

Error 301 may be transient, so a bounded retry can be appropriate when the
failed operation is safe to repeat and no write has succeeded. A retry policy
should account for contention and use a short backoff.

Do not blindly retry 306 or 512. Re-read the current record and re-evaluate
the intended change because the data changed after the script's earlier read.
When a captured native error is deliberately handled without creating an
application error, clear it through `FMError.Clear` before continuing, as
specified in `error-framework.md`.

## Multi-Record Transactions

The modern path for modifying multiple records atomically is `Open Transaction` **(step)** paired with `Commit Transaction`. Within a transaction block, multiple records can be opened, modified, and committed together — if any step fails, the entire transaction can be rolled back.

`Open Record/Request` **(step)** has no options — it is a self-closing step that simply attempts to acquire the write lock on the current record. Within an `Open Transaction` block, each `Open Record/Request` call adds that record to the transaction scope. If any record cannot be locked, the developer can revert the entire transaction.

**Important:** outside of an `Open Transaction` block, there is no native multi-record rollback. If Record A commits successfully and Record B's commit fails, Record A's changes are permanent. This is why `Open Transaction` is the preferred approach for coordinated multi-record writes.

## Audit Logging with OnWindowTransaction

`OnWindowTransaction` is a **file-level script trigger** (introduced in FM 20.1) that fires after a transaction is successfully committed. It creates a JSON object containing the file name, base table name, record ID, operation type ("New", "Modified", or "Deleted"), and the contents of a designated payload field for every operation within the completed transaction.

Key behaviors:

- Fires after the commit, not before — the data is already written when the trigger runs.
- Covers **all tables in the file** where the trigger is enabled — you cannot filter by table at the trigger level (filter in the processor script instead).
- The **payload field** (default name `onWindowTransaction`, configurable) should be an unstored calculation set to "evaluate always" that returns JSON with pertinent record data. Keep it lean — this evaluates on every record modification.
- The processor script runs at the **end of the script stack**.
- **Do not log to a table in the same file** — this creates recursive trigger invocations. Use a separate log file.
- `Truncate Table` does not fire the trigger. Imports do.
- FileMaker Data API and OData calls do not directly fire OnWindowTransaction, but scripts invoked by Data API or OData can trigger it.
- Performance impact is small for individual operations (~2,500 microseconds per record) and drops further (~700 microseconds) when operations are batched inside an `Open Transaction` / `Commit Transaction` block.

For full documentation, see the [Claris help for OnWindowTransaction](https://help.claris.com/en/pro-help/content/onwindowtransaction.html).

## Design Principles

- **Minimize open-record duration.** Compute values in variables before opening the record, then set fields and commit quickly.
- **Optionally use card windows for editing.** The record opens when the card opens, commits when it closes — the main layout context stays committed.
- **Separate read and write contexts.** List views should be read-only; editing happens in a card or detail layout via explicit action.
- **Accumulate input in globals or variables.** Write to the record only at the point of confirmed submission.
- **Run batch processes off-hours** when possible. When not possible, minimize lock duration and implement retry logic.
- **Log every failure in server-side scripts.** PSOS and scheduled scripts have no UI — write failures to a log table with record ID, timestamp, and error code.

## References

| Name                            | Type     | Local doc                                                           | Claris help                                                                                                 |
| ------------------------------- | -------- | ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Set Error Capture               | step     | `agent/docs/filemaker/script-steps/set-error-capture.md`            | [set-error-capture](https://help.claris.com/en/pro-help/content/set-error-capture.html)                     |
| Open Record/Request             | step     | `agent/docs/filemaker/script-steps/open-record-request.md`          | [open-record-request](https://help.claris.com/en/pro-help/content/open-record-request.html)                 |
| Set Field                       | step     | `agent/docs/filemaker/script-steps/set-field.md`                    | [set-field](https://help.claris.com/en/pro-help/content/set-field.html)                                     |
| Commit Records/Requests         | step     | `agent/docs/filemaker/script-steps/commit-records-requests.md`      | [commit-records-requests](https://help.claris.com/en/pro-help/content/commit-records-requests.html)         |
| Revert Record/Request           | step     | `agent/docs/filemaker/script-steps/revert-record-request.md`        | [revert-record-request](https://help.claris.com/en/pro-help/content/revert-record-request.html)             |
| Open Transaction                | step     | `agent/docs/filemaker/script-steps/open-transaction.md`             | [open-transaction](https://help.claris.com/en/pro-help/content/open-transaction.html)                       |
| Commit Transaction              | step     | `agent/docs/filemaker/script-steps/commit-transaction.md`           | [commit-transaction](https://help.claris.com/en/pro-help/content/commit-transaction.html)                   |
| Pause/Resume Script             | step     | `agent/docs/filemaker/script-steps/pause-resume-script.md`          | [pause-resume-script](https://help.claris.com/en/pro-help/content/pause-resume-script.html)                 |
| FMError.Clear                   | custom function | `agent/docs/knowledge/error-framework.md`                            | —                                                                                                        |
| Get ( RecordModificationCount ) | function | `agent/docs/filemaker/functions/get/get-recordmodificationcount.md` | [get-recordmodificationcount](https://help.claris.com/en/pro-help/content/get-recordmodificationcount.html) |
| OnWindowTransaction             | trigger  | —                                                                   | [onwindowtransaction](https://help.claris.com/en/pro-help/content/onwindowtransaction.html)                 |
