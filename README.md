# AURA Simulation

AI-powered elderly assistance robot simulation built with Python and Pygame.

## Overview

AURA Simulation demonstrates how an assistive home robot can combine smooth motion, rule-based AI, natural language command handling, and emergency response behavior in a single modular simulation.

## Features

- Voice-controlled AI robot (microphone-triggered command input)
- Elderly assistance task system (bring water, come to person, help flows)
- Emergency detection and priority override (fall response behavior)
- Task planning and execution pipeline (intent -> steps -> robot actions)
- Pathfinding and obstacle avoidance in a house-like environment
- Battery management and auto-charging behavior

## Project Structure

```text
.
├── main.py
├── config.py
├── ai_brain.py
├── voice.py
├── nlp.py
├── command_parser.py
├── core/
├── robot/
├── environment/
└── ui/
```

## Installation

1. Clone or download this repository.
2. Create and activate a virtual environment (recommended):

```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install core dependencies:

```bash
pip install -r requirements.txt
```

4. Optional: install voice dependencies:

```bash
pip install -r requirements-voice.txt
```

## Run

```bash
python3 main.py
```

## GitHub Pages Note

GitHub Pages serves static web content.  
This project is a desktop Python + Pygame simulation, so it does not auto-run directly inside a GitHub web page.

To view the full simulation:

```bash
python3 main.py
```

If you want, the next upgrade step is a browser build pipeline (PyGBag/WebAssembly) so visitors can run a web demo.

## Future Scope

- Integrate with real robot hardware
- Add cloud-backed AI planning layer
- Mobile app and caregiver dashboard integration
- Smart-home device connectivity
- Advanced multi-room and multi-agent coordination
