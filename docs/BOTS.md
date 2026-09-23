# Computer opponents and headless matches

The `economy`, `engine` and `attack` profiles implement the same decision interface as human players. They are heuristics, not expert opponents. Profiles adapt to the selected supply and known card gains/trashes; they cannot see authoritative decks or opponents' hands.

- **Economy:** favours treasure income with a limited number of useful actions.
- **Engine:** favours drawing, extra actions, deck improvement and reusable action chains.
- **Attack:** values disruption while still buying income and victory cards.

All profiles switch toward points as the main victory pile runs out. Shared decision handling selects useful cards, protects a minimum purchasing economy when trashing, orders draws, handles optional reactions and respects the engine's current option constraints.

`STRATEGY_REGISTRY` maps names to strategies ranking legal gains. `choose(view, decision, BotState)` returns `BotChoice(command, state)` without modifying the view or old bot memory. A saved bot state contains its profile, strategy version, independent seed and decision count. Random tie breaks use that private stream; they never consume gameplay randomness. Strategies derive known ownership from initial cards and public gain/trash events.

## Reproducible runs

```bash
scripts/simulate.sh --seed 42 --games 5 --players 3 --profiles economy engine attack
scripts/simulate.sh --seed 42 --games 5 --players 4 --profiles attack --kingdom random
scripts/simulate.sh --seed 42 --max-decisions 1
```

Profiles cycle across seats when fewer are supplied than players. `--kingdom` accepts `preset`, `random`, or ten distinct comma-separated stable Kingdom IDs. Random selection is deterministic and separate from gameplay randomness. Successive games use successive seeds.

The JSON result records each seed, supply, profiles, decisions, turns and completion status. Finished games include scores and winners; unfinished games preserve empty final results. The process exits 1 if any game exhausts `--max-decisions` (default 4000), and 0 when all finish. It does not invent a timeout winner or alter game rules. Invalid configuration exits 2.

Preserve the seed, supply and profiles when reporting a failure. For behaviour comparisons, run the same configurations before and after the change; heuristic win rates are observations rather than correctness assertions.
