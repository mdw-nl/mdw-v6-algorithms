Every server/store/node config is templated directly in `../scripts/devnet.py` rather
than kept as static files here, since every value in them is already a constant at the
top of that script. This directory exists for AGENTS.md §2's prescribed layout and as
the place to add genuinely static config later (e.g. a `--extra-node-config` snippet)
if that need ever arises.
