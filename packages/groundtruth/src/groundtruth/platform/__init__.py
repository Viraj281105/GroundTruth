"""The GroundTruth platform: everything that makes the engine a real application.

**Owner: Bhumi.** API, database, case management, analysis job lifecycle,
dataset services, storage, evidence persistence, report generation, GenAI
integration, deployment and operations.

The platform consumes the engine through the contract and nothing else::

    from groundtruth.contracts import AnalysisRequest, AnalysisResult
    from groundtruth.engine import run_analysis

    result = run_analysis(request, data_access)

It never imports from ``groundtruth.engine.<submodule>``. A test enforces this.
"""
