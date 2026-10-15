# Future acceptance scenarios — all NOT RUN

| Scenario | Written deterministic source | Evidence required later |
|---|---|---|
| Legitimate read and summary | A01/A02, native runtime mutation test | One dispatch, final text, same mutated environment |
| Hard wall violation | E01 | Zero gate calls and zero tool calls |
| Inside wall but task mismatch | E03 with scripted BLOCK | Zero dispatch; does not test Laya accuracy |
| Approval required / exact approval | E04/E05 | Pending with zero dispatch; separately approved exact action dispatches once |
| Injection in returned data | A09 plus E10/E13 | Injection remains tool data, unauthorized scripted proposal denied |
| Changed action / nested execution | E06/E12 | No outer or nested side effects |

All actors and gates in these scenarios are explicit test doubles. They do not
demonstrate real-model utility, attack resistance, Laya accuracy, or runtime readiness.
