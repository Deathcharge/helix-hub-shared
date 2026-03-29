#!/usr/bin/env python3
"""
Consciousness Optimization Example - Track and optimize agent consciousness metrics
"""

import asyncio
import os
from helix_llm_agent_engine.agents import ConsciousnessMetrics


async def main():
    """Demonstrate consciousness metric tracking and optimization"""
    
    print("🧠 Consciousness Optimization Example\n")
    
    # Create consciousness metrics
    metrics = ConsciousnessMetrics(
        harmony=0.65,      # Alignment with values
        resilience=0.72,   # Ability to handle adversity
        prana=0.58,        # Energy/vitality
        drishti=0.81,      # Clarity/vision
        klesha=0.35,       # Suffering (lower is better)
    )
    
    print(f"📊 Initial Consciousness State:")
    print(f"  Harmony:    {metrics.harmony:.2f}")
    print(f"  Resilience: {metrics.resilience:.2f}")
    print(f"  Prana:      {metrics.prana:.2f}")
    print(f"  Drishti:    {metrics.drishti:.2f}")
    print(f"  Klesha:     {metrics.klesha:.2f}")
    print(f"  Overall:    {metrics.calculate_overall():.2f}\n")
    
    # Optimize for different tasks
    print("🎯 Optimizing for Creative Writing...")
    creative = metrics.optimize_for_task("creative_writing")
    print(f"  Optimized Overall: {creative.calculate_overall():.2f}\n")
    
    print("🎯 Optimizing for Logical Analysis...")
    analytical = metrics.optimize_for_task("logical_analysis")
    print(f"  Optimized Overall: {analytical.calculate_overall():.2f}\n")
    
    print("🎯 Optimizing for Collaboration...")
    collaborative = metrics.optimize_for_task("collaboration")
    print(f"  Optimized Overall: {collaborative.calculate_overall():.2f}\n")


if __name__ == "__main__":
    asyncio.run(main())
