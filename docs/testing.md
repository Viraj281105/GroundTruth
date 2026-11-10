# Testing Guide & Quality Assurance Protocols

**Backend Suite**: 2,130+ automated offline Python tests (`pytest`, `hypothesis`)  
**Frontend Suite**: 746 automated TypeScript tests across 75 files (`vitest`, Playwright, React Testing Library)  
**CI Gate**: Ruff, Mypy, AST Boundary Checker, OpenAPI Snapshot Verifier.

```mermaid
graph TD
    subgraph TestExecution["Continuous Integration Test Matrix"]
        Pytest["Backend Unit & Integration (2,130+ Offline Tests)<br/>• Contract Boundaries (AST Check)<br/>• SCM Injected Effect Recovery<br/>• Units Guard (NDVI != Carbon)<br/>• GenAI Grounding Gate"]
        Hypothesis["Hypothesis Property Suites<br/>• Simplex Constraint Preservation<br/>• Non-Negative Weight Bounds"]
        FrontendVitest["Frontend Unit Suite (746 Tests / 75 Files)<br/>• Design System Components (ds/)<br/>• Persona Workspace Routing<br/>• Cross-Org Denial Guards"]
        PlaywrightE2E["Playwright Visual Regression<br/>• Desktop (1280px) & Mobile (375px)"]
    end

    Pytest --> CIReport["Consolidated Verification Report"]
    Hypothesis --> CIReport
    FrontendVitest --> CIReport
    PlaywrightE2E --> CIReport
```

![Auditor Dashboard](product/screens/auditor-dashboard.png)

---

## 1. Backend Python Testing (2,130+ Offline Tests)

```bash
# Execute complete offline backend test suite (live network tests require --run-network)
pytest

# Verify golden Kariba reproducibility benchmark
pytest tests/test_golden_reproducibility.py
```

---

## 2. Frontend Web Testing (746 Tests / 75 Files)

From `apps/web/`:

```bash
# Run 746 automated unit and component tests
npm test -- --run

# Validate TypeScript compilation without errors
npm run typecheck

# Verify frontend types match backend OpenAPI specification
npm run check:api-types

# Run Playwright End-to-End visual tests
npm run test:e2e
```
