# Copia

## Project purpose

Copia is a personal AI assistant that will gradually evolve from a simple task-oriented assistant into a cross-device agent.

## First-stage scope

- A Python-based project.
- A separate service responsible for LLM API communication and agent logic.
- Support for multiple LLM providers behind a provider-agnostic interface.
- A React and TypeScript web client with a simple chat UI for communicating with an LLM.
- A future Tauri 2 wrapper for the same client on desktop and mobile targets.

## Long-term direction

Copia will add memory management, context management, planning, tool orchestration, voice interaction, and native macOS and Android clients. The server-side agent logic must remain independent from the client UI and the selected LLM provider.

## Development principles

- Build the smallest useful vertical slice first.
- Keep provider-specific API code outside the core agent logic.
- Add integrations and configuration only when required by a concrete use case.
- Do not introduce secrets into the repository.
