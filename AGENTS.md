# AGENTS.md

## Project overview

This repository contains educational and demonstration programs for Raspberry Pi 4 and LEGO SPIKE Prime using RasPike-ART.

The system consists of:

- C applications for robot control
- Python camera and vision servers
- A Flask-based web dashboard
- Bash scripts for building, running, and configuring the system
- Documentation for instructors and students

Primary use cases are laboratory exercises, student development, open-campus activities, and demonstrations.

Prioritize safety, compatibility, maintainability, and educational clarity.

## Repository structure

- `robot/`: RasPike-ART applications written in C
- `vision-server/`: Camera processing, line detection, marker tracking, and PWM control
- `dashboard/`: Flask web UI and systemd integration
- `scripts/`: Build, startup, shutdown, network, and setup utilities
- `docs/`: Design documents and student instructions

Important robot applications:

- `robot/ocan2026/`: Introductory sensor-based line tracing
- `robot/direct_pwm_camera/`: Receives motor PWM commands from a Python TCP server
- `robot/line_trace_camera/`: Legacy camera-based line tracer

## Source of truth

Inspect the current implementation before making changes.

Some documentation describes earlier implementations and may be outdated.

In particular:

- Robot applications are built from source directories under `robot/`.
- `scripts/build-robot` uses the external RasPike-ART workspace.
- The current build mechanism uses `make img=...`, not the older copy-based `make app=...` workflow.
- `docs/dashboard-proposal.md` is an initial design proposal, not necessarily the current implementation.

When documentation conflicts with code, verify the intended behavior and update documentation accordingly. Do not silently change established behavior merely to match outdated documentation.

## Development environment

The target environment is a Raspberry Pi running Linux, with a separately installed RasPike-ART SDK.

The expected SDK location is:

`~/RasPike-ART/sdk/workspace`

The SDK itself is not included in this repository.

Do not copy SDK sources, locally generated binaries, machine-specific configuration, credentials, or virtual environments into the repository.

Do not assume that Raspberry Pi hardware, SPIKE Prime, Picamera2, or the RasPike-ART SDK is available in the development environment.

## Robot control and safety

Safety-sensitive behavior must be preserved unless a change is explicitly requested and reviewed.

Requirements include:

- Keep motor PWM commands within the supported range of -100 to 100.
- Preserve motor stop behavior on communication failure.
- Preserve pause and emergency-stop behavior.
- Avoid unintended motor activation during startup or shutdown.
- Preserve documented sensor and motor port assignments unless explicitly changing the hardware configuration.
- Do not introduce uncontrolled automatic robot execution.
- Treat changes to communication protocols and timing as potentially safety-critical.

For hardware-related changes, distinguish static validation from actual hardware verification.

Never claim that robot behavior has been tested on real hardware unless such testing was actually performed.

## Python vision servers

The Python vision servers communicate with robot applications using TCP.

Important compatibility constraints:

- The existing control protocol must remain compatible unless a deliberate migration is approved.
- Preserve documented PWM limits and stop behavior.
- Keep line-tracing and marker-control functionality distinct.
- Avoid simultaneous use of the same camera by conflicting services.
- Maintain backward compatibility where existing clients depend on legacy requests or responses.

Avoid unnecessary camera initialization or hardware access during unit tests.

Prefer extracting testable computational logic from hardware-dependent code.

## Dashboard and system services

The dashboard uses Flask and systemd services to manage demonstration programs.

The registered programs and ports are defined in:

`dashboard/programs.json`

Current web ports are:

- 8080: Line tracing vision server
- 8081: Marker controller
- 8082: Dashboard

Treat these as current defaults, not immutable architectural requirements.

When changing ports, service names, or program registration, inspect and update all affected files consistently.

Security requirements:

- Do not implement arbitrary shell-command execution from the dashboard.
- Keep system operations restricted to explicitly permitted commands and services.
- Preserve CSRF protection for state-changing requests.
- Do not broaden passwordless sudo permissions without explicit approval.
- Preserve service exclusivity and predictable start/stop behavior.
- Do not expose unnecessary services or sensitive information.

## Build and execution

Use the existing build and startup mechanisms.

Relevant scripts include:

- `scripts/build-robot`
- `scripts/start-robot`
- `scripts/start-vision`
- `scripts/start-marker-controller`
- `scripts/install-dashboard-program-units`

Inspect script behavior before changing it.

Do not replace the current build system or modify the external RasPike-ART installation without a specific requirement.

A successful build must be distinguished from the presence of an older executable.

Do not run robot motors, install systemd services, modify network connections, reboot, or power off a machine merely as part of routine verification.

Such operations require explicit authorization.

## Testing

Prefer automated tests that do not require physical hardware.

Existing test locations include:

- `dashboard/tests/`
- `vision-server/tests/`

For Python changes, run the relevant existing tests and add regression tests where appropriate.

Typical commands, when dependencies are available:

```bash
python3 -m unittest discover -s dashboard/tests -v
python3 -m pytest vision-server/tests -q
```

For Python syntax checks:

```bash
python3 -m compileall -q dashboard vision-server
```

For Bash scripts, use non-destructive syntax validation where applicable:

```bash
bash -n scripts/build-robot
bash -n scripts/setup
```

Check shell syntax only for scripts actually intended to run with Bash.

For C changes, use the established RasPike-ART build environment when available.

If the SDK or hardware is unavailable, report the limitation instead of claiming complete verification.

Do not introduce a large new testing framework when the existing infrastructure is sufficient.

## Educational requirements

This is an educational repository.

Prefer code that students and instructors can understand and modify.

For beginner-oriented programs, especially `robot/ocan2026/`, preserve the simplicity of the exercises.

Avoid unnecessary abstractions, dependencies, or architectural complexity.

Keep examples, comments, and instructions consistent with actual behavior.

Documentation intended for students should be understandable to beginners.

Use Japanese for student-facing documentation unless otherwise requested. Existing identifiers and protocol names may remain in English.

## Network and machine configuration

Scripts such as `scripts/setup`, `scripts/net-ap`, and `scripts/net-wifi` may modify persistent machine settings.

Treat changes to these scripts as high risk.

Preserve:

- Robot-specific identity configuration
- Predictable IP address assignment
- Existing unrelated network profiles
- SSH accessibility and recovery options
- Explicit confirmation before disruptive operations

Do not run these scripts during automated testing.

Do not regenerate machine identities or SSH host keys without an explicit requirement.

## Git workflow

Before making changes, inspect the current repository state and relevant files.

- Do not overwrite or discard uncommitted changes.
- Do not use destructive Git operations without explicit authorization.
- Keep changes focused on the requested task.
- Avoid unrelated formatting or refactoring.
- Do not commit secrets, local configuration, generated binaries, or runtime data.

Unless instructed otherwise:

1. Work on a dedicated branch.
2. Implement the smallest reasonable change.
3. Run applicable tests.
4. Document limitations and unverified hardware behavior.
5. Create a Draft Pull Request.
6. Do not merge into `main` automatically.

The Pull Request description should include:

- Purpose and background
- Summary of changes
- Files or components affected
- Tests performed and results
- Tests not performed and why
- Hardware verification still required
- Potential compatibility or safety risks

## Scope and decision-making

Do not expand the scope of a task without a clear reason.

Small bug fixes may be implemented directly.

For significant changes to architecture, robot control, networking, security, or the student workflow, explain the proposed approach and tradeoffs before implementation.

Preserve behavior outside the requested change.

When uncertain, favor a minimal, reversible modification.

## Final report

At the end of each task, report:

- What changed
- What was tested
- What could not be tested
- Any remaining risks
- Pull Request URL, if created

Never describe unperformed tests as passed.
