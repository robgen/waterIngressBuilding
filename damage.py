#!/usr/bin/env python3
"""Helpers for mapping simulated water depths to loss estimates."""

import bisect
import csv
from dataclasses import dataclass


@dataclass(frozen=True)
class VulnerabilityCurve:
    """Piecewise-linear loss curve defined over water depth."""

    heights_m: list
    losses: list
    loss_column: str = 'mean_repair_loss_GBP'

    def interpolate_loss(self, height_m):
        """Return the linearly interpolated loss at a given water depth."""
        if not self.heights_m or not self.losses:
            raise ValueError('Vulnerability curve is empty')

        x = float(height_m)
        if x <= self.heights_m[0]:
            return float(self.losses[0])
        if x >= self.heights_m[-1]:
            return float(self.losses[-1])

        idx = bisect.bisect_right(self.heights_m, x) - 1
        x0 = self.heights_m[idx]
        x1 = self.heights_m[idx + 1]
        y0 = self.losses[idx]
        y1 = self.losses[idx + 1]

        if x1 == x0:
            return float(y0)

        frac = (x - x0) / (x1 - x0)
        return float(y0 + frac * (y1 - y0))


def load_vulnerability_curve(filepath, depth_column='height_m',
                             loss_column='mean_repair_loss_GBP'):
    """Load a depth-loss curve from CSV and average duplicate heights."""
    grouped = {}

    with open(filepath, newline='') as f:
        reader = csv.DictReader(row for row in f if row.strip() and not row.lstrip().startswith('#'))
        if reader.fieldnames is None:
            raise ValueError(f'No header found in vulnerability file: {filepath}')
        if depth_column not in reader.fieldnames:
            raise ValueError(
                f'Missing depth column "{depth_column}" in vulnerability file: {filepath}'
            )
        if loss_column not in reader.fieldnames:
            raise ValueError(
                f'Missing loss column "{loss_column}" in vulnerability file: {filepath}'
            )

        for row in reader:
            try:
                height = float(row[depth_column])
                loss = float(row[loss_column])
            except (TypeError, ValueError):
                continue
            grouped.setdefault(height, []).append(loss)

    if not grouped:
        raise ValueError(f'No valid vulnerability data found in: {filepath}')

    heights = sorted(grouped.keys())
    losses = [sum(grouped[h]) / len(grouped[h]) for h in heights]
    return VulnerabilityCurve(heights_m=heights, losses=losses, loss_column=loss_column)
