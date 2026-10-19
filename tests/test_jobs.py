"""Research in a real background thread while the UI reads the same database (what happens in the app)."""
import time

from eia import views
from eia.agent import ResearchAgent
from eia.db import Store
from eia.demo import DEMO_COMPANY, SyntheticFetcher, demo_search
from eia.jobs import JobRegistry
from eia.providers.llm import NullLLM


def test_background_job_completes_while_ui_reads(tmp_path, monkeypatch):
    monkeypatch.delenv("EIA_SYNC_JOBS", raising=False)
    st = Store(str(tmp_path / "jobs.sqlite"))
    reg = JobRegistry()

    def work(job):
        agent = ResearchAgent(st, search=demo_search(), llm=NullLLM(), fetcher=SyntheticFetcher(), progress=job.progress)
        return agent.research(DEMO_COMPANY, mode="demo")

    job = reg.start("demo", work)
    reads = 0
    deadline = time.time() + 60
    while not job.done and time.time() < deadline:  # the page keeps reading while research writes
        for r in st.list_runs():
            views.run_summary(st, r.id)
            views.findings_df(st, r.id)
        reads += 1
    assert job.done and job.status == "completed", (job.status, job.error)
    assert job.run_id and st.get_run(job.run_id).status == "completed"
    assert job.frac == 1.0 and job.messages and reads >= 1
    assert not reg.active() and reg.running_run_ids() == set()


def test_failed_job_reports_error_instead_of_hanging():
    reg = JobRegistry()

    def boom(job):
        raise RuntimeError("network down")

    job = reg.start("x", boom)
    for _ in range(100):
        if job.done:
            break
        time.sleep(0.02)
    assert job.done and job.status == "failed" and "network down" in job.error
