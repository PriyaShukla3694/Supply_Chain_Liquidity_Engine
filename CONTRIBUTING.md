# Contributing Guidelines

Welcome to the Supply Chain Liquidity Engine project! To maintain code quality and smooth collaboration, please follow our Git workflow standards.

## Branching & Pull Request Workflow

1. **Branch Hierarchy**:
   - `main`: Production-ready code only. Never commit directly to `main`.
   - `develop`: Integration branch for upcoming features and releases.
   - `feature/*`: Feature branches created off `develop` (e.g., `feature/db-schema`, `feature/risk-model`).

2. **Standard Workflow**:
   - Create your feature branch from `develop`:
     ```bash
     git checkout develop
     git pull origin develop
     git checkout -b feature/your-feature-name
     ```
   - Commit your changes locally with descriptive commit messages.
   - Push your feature branch to GitHub:
     ```bash
     git push -u origin feature/your-feature-name
     ```
   - Open a **Pull Request (PR)** targeting the `develop` branch (`feature/*` -> PR -> `develop` -> PR -> `main`).

3. **Code Review Rules**:
   - **Never commit directly to `main`**.
   - Every Pull Request requires **at least one review from a teammate** prior to merging.
   - All unit and integration tests must pass prior to merge.
