# Screening logic in plain English

[Back to the sharing page](../README.md)

## 1. Start with a suitable industry reference group

The saved models cover six broad pools of related TSIC activities. The actual represented codes are in [industry_scope.json](../industry_scope.json). A company outside that scope is not forced into a similar industry. FY2021–FY2025 are the supported financial years.

Company functions, assets, risks, group relationships and commercial explanations cannot be established from an industry code alone.

## 2. Run three financial checks in parallel

- **Masked reconstruction:** can the other figures predict one financial measure? Larger observed-target errors indicate an unfamiliar relationship.
- **Autoencoder:** can the overall financial pattern be compressed and reconstructed? Larger reconstruction error indicates an unfamiliar pattern.
- **Isolation Forest:** is the financial record easier to isolate from peers? Higher reported anomaly scores indicate more unusual combinations.

They do not pass predictions from one model to another. Each uses saved, training-fitted preprocessing. K-means is retained as preliminary descriptive metadata and does not supply a final risk score.

## 3. Put their different scores on a common scale

For each method, rank the raw score against that method’s industry calibration scores. A percentile of 0.93 means that 93% of the reference scores are at or below it. It does **not** mean a 93% chance of a tax error.

The consensus is:

`(masked percentile + autoencoder percentile + Isolation Forest percentile) / 3`

Weights are one-third each for transparency. They were not learned from verified tax outcomes and are not claimed to be optimal. The two reconstruction methods may provide correlated evidence.

## 4. Apply the saved cutoff

Flag a financial pattern only when `consensus > industry cutoff`. Equality does not flag it. The cutoff is the higher observed 95th-percentile calibration consensus score, not a statutory limit and not always the number 0.95.

| Industry | Consensus cutoff (rounded) |
|---|---:|
| Electronics manufacturing | 0.936667 |
| Electronics trading | 0.930159 |
| IT services | 0.927273 |
| Printing | 0.922222 |
| Accounting/back office | 0.933333 |
| Transport/logistics | 0.928571 |

The program compares full-precision values. It does not require two individual method flags to agree. Additional financial indicators use training-peer lower/upper deciles, prior losses, debt-service proxies and zero-revenue context. They remain supporting review facts.

## 5. Assess company-specific concerns independently

A Yes to an applicable risk question raises Higher concern. Missing notes or an unavailable financial comparison do not suppress the Yes. If there is no risk Yes, incomplete required information yields More information needed; all applicable risks No plus complete required context yields Less concern for this rule component.

Profile choices and background confirmations are descriptive. They do not automatically indicate risk. The recorded functional profile may overlap others; selecting Routine entity does not imply a guaranteed return or a blanket prohibition on losses.

## 6. Keep the reviewer’s judgement visible

A reviewer may find a defensible commercial explanation for a financial flag, supported by the relevant evidence. The prototype does not automatically erase the original flag or make a tax-compliance determination. Its conservative checklist is a starting point for review, not an official HMRC scoring formula.

There are no verified TP-outcome labels, so accuracy at detecting tax errors is unknown. The reference pool is limited to available observations in six industries. Adding suitable companies and recalibrating could change which observations are flagged.
