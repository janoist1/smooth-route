# Road Quality AI: Training Data Guide

To improve the AI's judgment and make it align better with your manual ratings, we need a high-quality dataset. Here are the recommendations for effective training.

## 1. Data Quantity
- **Initial Target**: Aim for at least **200-300** high-quality manual ratings (Ground Truth).
- **YOLO Training**: For the AI to truly "learn" from your style, we ideally need **500-1,000** annotated images with bounding boxes.
- **Incremental Improvement**: You don't need all at once. Even 50-100 new reviewed items per week will significantly improve the system over time.

## 2. Qualitative Quality (What to rate?)
The AI learns from your "Ground Truth". To help it:
- **Balance the Scale**: Don't just rate the bad roads. We need many examples of "Perfect" (1.0) and "Good" (2.0) roads so the AI learns what *isn't* a problem.
- **Edge Cases**: Rate roads that are "borderline" (e.g., a road with many patches but a smooth ride).
- **Diversity**: Mix your data!
    - Different times of day (shadows are a big factor).
    - Different road colors (new black asphalt vs old grey concrete).
    - Different weather conditions (wet roads reflect light differently).

## 3. What makes a "Good" Training Image?
- **Visibility**: The road surface should be clear in the bottom 40% of the image.
- **Context**: If a pothole is small but deep, try to mark it clearly. If it's just a shallow dip, your rating should reflect that it's less severe.
- **Consistency**: Try to be consistent. If you rate a road with one small crack as "2.0 Good" today, try not to rate a similar one as "3.0 Fair" tomorrow.

## 4. Current Scale Definition (Recall)
- **1.0 (Excellent)**: Brand new or recently resurfaced. No visible defects.
- **2.0 (Good)**: Minor wear, small cracks, or high-quality patches that don't affect driving.
- **3.0 (Fair)**: Medium wear, visible alligator cracks, or small potholes that are noticeable.
- **4.0 (Poor)**: Significant damage, deep potholes, or very rough surface.
- **5.0 (Very Poor)**: Immediate repair needed. Multiple deep potholes or destroyed surface.
