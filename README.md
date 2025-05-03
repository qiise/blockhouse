# blockhouse

Cont &amp; Kukanov Back-testing Trial Task

## Structure of Code:

-**`process_data`** : reads and preprocesses the market data provided in the csv into venue snapshots

-**`allocate`**: implements the Cont-Kukanov allocator in order to split orders

-**`backtest`** : simulates execution over time using the Cot-Kukanov allocator

-**Baseline Strategies**: 'baseline1' is for best ask, 'baseline2' is for TWAP, and 'baseline3' is for VWAP. These are used for comparison

-**Parameter Tuning** : Perform a grid search over 'lambda_over', 'lambda_under', and 'queue_risk'

## Choices Made for Searching:

- **`lambda_over`**: Tested values `[0.0, 0.01, 0.05]` to penalize overfilling.

- **`lambda_under`**: Tested values `[0.01, 0.05, 0.1]` to penalize underfilling.

- **`queue_risk`**: Tested values `[0.0, 0.001, 0.005]` to account for queue risk.

## Suggested Improvement:

Implementing queue position dynamics in order to better model limit order fills. The current allocator assumes that orders are filled if they are within the displayed size, but queue position affects execution probability. Therefore, a more realistic model would make sure to track queue positions and adjust the fill probabilities according to this as well.
