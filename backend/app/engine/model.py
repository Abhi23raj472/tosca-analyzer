"""In-memory model of a Tosca workspace subset.

The engine package uses only the Python standard library so the same code runs
on the server (FastAPI) and in the browser demo (Pyodide).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class StepValue:
    name: str
    value: str = ""
    action_mode: str = "Input"  # Input | Verify | WaitOn | Buffer | Select | Insert | Constraint ...
    data_type: str = "String"
    disabled: bool = False

    def render(self) -> str:
        return f"{self.name} = {self.value}   (ActionMode: {self.action_mode})"


@dataclass
class TestStep:
    id: str
    name: str
    kind: str = "step"  # step | reference
    module: str = ""
    values: list[StepValue] = field(default_factory=list)
    disabled: bool = False
    folder_path: list[str] = field(default_factory=list)  # TestStepFolders inside the TestCase
    reference: Optional[str] = None  # name of the Reusable TestStepBlock for kind == reference
    index: int = 0  # 1-based position inside the test case

    def signature(self) -> tuple:
        """Stable identity used to find copy-pasted step sequences."""
        vals = tuple((v.name.lower(), v.action_mode.lower(), v.value) for v in self.values)
        return (self.kind, (self.module or self.name).lower(), vals)

    def text(self) -> str:
        parts = [self.name, self.module, self.reference or ""]
        for v in self.values:
            parts += [v.name, v.value, v.action_mode]
        return " ".join(p for p in parts if p)


@dataclass
class TestCase:
    id: str
    name: str
    path: list[str] = field(default_factory=list)  # folder breadcrumb above the test case
    description: str = ""
    steps: list[TestStep] = field(default_factory=list)
    properties: dict = field(default_factory=dict)
    requirement_keys: list[str] = field(default_factory=list)

    @property
    def breadcrumb(self) -> str:
        return " › ".join(self.path + [self.name])

    @property
    def top_folder(self) -> str:
        return self.path[0] if self.path else self.name


@dataclass
class ReusableBlock:
    id: str
    name: str
    parameters: list[str] = field(default_factory=list)
    steps: list[TestStep] = field(default_factory=list)


@dataclass
class Workspace:
    name: str
    test_cases: list[TestCase] = field(default_factory=list)
    blocks: list[ReusableBlock] = field(default_factory=list)
    config_params: dict = field(default_factory=dict)
    recovery_scenarios: list[str] = field(default_factory=list)
    cleanup_scenarios: list[str] = field(default_factory=list)
    source_format: str = "xml"
    warnings: list[str] = field(default_factory=list)

    @property
    def step_count(self) -> int:
        return sum(len(tc.steps) for tc in self.test_cases)

    def to_dict(self) -> dict:
        return asdict(self)
