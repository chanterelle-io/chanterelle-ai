# MVP Smoke Test

This smoke test provides a repeatable acceptance pass for the current MVP against the live local stack.

## Setup

1. Start infrastructure with `make infra`.
2. Run the required migrations for your database state.
3. Run `make seed`.
4. Start the services in separate terminals:
   `make artifact`, `make runtime-sql`, `make runtime-python`, `make execution`, `make agent`.

## Run

```bash
make smoke-mvp
```

## Coverage

- Agent `/chat` round-trip on a bounded SQL request
- Direct SQL execution and artifact registration
- Python transform using a prior artifact as input
- Topic-scoped finance policy denial for `python_transform`
- Deferred execution and job completion for a large SQL query
- Artifact quota visibility plus pin/unpin retention controls

## Expected Result

The command prints six numbered steps and ends with:

```text
MVP smoke test passed.
```