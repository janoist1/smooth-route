# RQI Correlation Report: Manual vs AI

I have analyzed the 221 reviewed items to understand why the statistics might feel incorrect.

## Key Findings
There is a significant discrepancy between manual ratings and AI predictions. In general, the **AI is much harsher** than your manual assessment.

### Categorical Agreement
Total Reviewed Items: 219 (with RQI)
- **Exact Category Match**: 22% (48 items)
- **Severe Disagreement (Good vs Poor)**: 35% (77 items)

### Confusion Matrix
(How your ratings map to AI predictions)

| Manual Rating | AI: GOOD | AI: FAIR | AI: POOR |
|---------------|----------|----------|----------|
| **GOOD**      | 11       | 14       | **75**   |
| **FAIR**      | 6        | 24       | 72       |
| **POOR**      | 2        | 2        | 13       |

## Analysis
- **The "Optimism Gap"**: You rated **101** items as GOOD (<= 2.0), but the AI only agreed on **11** of them. The AI categorized **75** of your "Good" roads as "Poor".
- **AI Thresholds**: The AI is extremely sensitive to potholes and cracks, often giving 4.0 or 5.0 to roads you consider acceptable.
- **Stats Behavior**: Because we prioritize manual ratings for statistics, the dashboard shows many "Good" items. However, since the AI remains harsh for unreviewed items, the rest of the map will look significantly worse.

## Recommendation
1. **Re-calibrate AI**: We should adjust the AI's weighted damage score to be less aggressive.
2. **Review Thresholds**: Confirm if 2.0 (Good) / 3.5 (Poor) are the correct cut-off points for the 1-5 scale.
