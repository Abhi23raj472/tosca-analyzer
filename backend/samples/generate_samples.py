"""Generate realistic sample inputs for demos and tests.

    python samples/generate_samples.py

Writes Claims_Regression.xml (48 test cases, with deliberate best-practice
problems), Claims_Run.xml (JUnit execution results) and CLM-1482.json (a JIRA
test issue with manual steps).
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from xml.sax.saxutils import quoteattr

OUT = Path(__file__).parent
random.seed(7)


def v(name, value="", mode="Input", dtype="String", disabled=False):
    extra = f' DataType="{dtype}"' if dtype != "String" else ""
    extra += ' Disabled="true"' if disabled else ""
    return f'<TestStepValue Name={quoteattr(name)} Value={quoteattr(value)} ActionMode="{mode}"{extra}/>'


def step(name, values, module=None, disabled=False):
    mod = f' Module={quoteattr(module or name)}'
    dis = ' Disabled="true"' if disabled else ""
    return f'<XTestStep Name={quoteattr(name)}{mod}{dis}>' + "".join(values) + "</XTestStep>"


def rtb_ref(user="{CP[ClaimsUser]}", pw="{CP[ClaimsPassword]}"):
    return ('<TestStepFolderReference Name="RTB_Login" Reference="RTB_Login">'
            f'<BusinessParameter Name="Username" Value={quoteattr(user)}/>'
            f'<BusinessParameter Name="Password" Value={quoteattr(pw)}/>'
            '</TestStepFolderReference>')


def copied_login(url):
    return [
        step("OpenUrl", [v("Url", url)]),
        step("Login Page", [v("Username", "claims_member01"), v("Password", "*****", dtype="Password")]),
        step("Login Page", [v("Login", "{Click}")]),
        step("Dashboard", [v("Dashboard Title", "My claims", "WaitOn")]),
    ]


def testcase(name, steps, desc="", key="", folders=None):
    props = f'<Properties><Property Name="JiraKey" Value="{key}"/></Properties>' if key else ""
    d = f' Description={quoteattr(desc)}' if desc else ""
    body = ""
    if folders:
        for fname, fsteps in folders:
            body += f'<TestStepFolder Name="{fname}">' + "".join(fsteps) + "</TestStepFolder>"
    else:
        body = "".join(steps)
    return f'<TestCase Name={quoteattr(name)}{d}>{props}{body}</TestCase>'


SCENARIOS = [
    ("Search claim by number", "Claim Search", [v("Claim Number", "CLM-2024-0091"), v("Search", "{Click}")],
     [v("Result Count", "1", "Verify")]),
    ("Filter claims by status", "Claim Search", [v("Status Filter", "Pending review"), v("Apply", "{Click}")],
     [v("First Row Status", "Pending review", "Verify")]),
    ("Update member address", "Member Profile", [v("Street", "12 Park Lane"), v("Save", "{Click}")],
     [v("Toast", "Address saved", "Verify")]),
    ("Download EOB", "Claim Detail", [v("Member ID", "M-10023"), v("Download EOB", "{Click}")],
     [v("Download Status", "Complete", "Verify")]),
    ("Appeal denied claim", "Appeal Form", [v("Reason", "Medically necessary"), v("Submit Appeal", "{Click}")],
     [v("Appeal Status", "Received", "Verify")]),
    ("Add dependent", "Dependents", [v("Dependent Name", "Asha Rao"), v("Date of Birth", "03/14/2016"), v("Add", "{Click}")],
     [v("Dependent Count", "2", "Verify")]),
    ("View claim history", "Claim History", [v("Member ID", "M-10023"), v("Period", "Last 12 months")],
     [v("History Table.Visible", "True", "Verify")]),
    ("Check deductible", "Benefits", [v("Member ID", "M-10023"), v("Plan Year", "2026")],
     [v("Deductible Met", "True", "Verify")]),
]


def build_workspace() -> str:
    tcs: list[str] = []
    n = 0

    # The test case the JIRA ticket CLM-1482 describes (mirrors the requirement-check screen).
    submit = [
        rtb_ref(),
        step("Dashboard", [v("Dashboard Title", "My claims", "Verify")]),
        step("Dashboard", [v("New Claim", "{Click}")]),
        step("Claim Form", [v("Member ID", "{XL[Member_ID]}"), v("Member Name", "{XL[Member_Name]}", "Verify")]),
        step("Claim Form", [v("Diagnosis Code", "{XL[Dx_Code]}"), v("Amount", "{XL[Amount]}"),
                            v("Error Banner.Visible", "False", "Verify")]),
        step("Claim Form", [v("Submit", "{Click}")]),
        step("TBox Wait", [v("Duration", "5000")], module="TBox Wait"),
        step("Confirmation", [v("Confirmation Text", "*Claim #*", "Verify")]),
        step("Claim Detail", [v("Claim Status", "Submitted", "Verify")]),
        step("Claim Detail", [v("Print Summary", "{Click}")]),
    ]
    tcs.append(testcase("Submit Claim", submit, "Member submits a medical claim with a supporting document.", "CLM-1482"))
    n += 1

    # 22 test cases with the login steps copied in; 14 of them also hard-code the environment URL.
    for i in range(22):
        name, screen, inputs, checks = SCENARIOS[i % len(SCENARIOS)]
        name = f"{name} – variant {i // len(SCENARIOS) + 1}"
        url = "https://qa2.example.internal/claims" if i < 14 else "{CP[BaseUrl]}/claims"
        body = copied_login(url) + [step(screen, inputs)]
        if i % 5 == 0:
            body.append(step("TBox Wait", [v("Duration", str(3000 + 1000 * (i % 3)))], module="TBox Wait"))
        if i % 4 != 3:  # a few of these never verify
            body.append(step(screen, checks))
        if i == 6:
            body.append(step("Old export check", [v("Export", "{Click}")], disabled=True))
        desc = "" if i % 3 == 0 else f"{name.split(' – ')[0]} for a claims member."
        tcs.append(testcase(name, body, desc, f"CLM-{1500 + i}" if i % 2 == 0 else ""))
        n += 1

    # 25 test cases built the recommended way: folders, the reusable login block, parameters.
    for i in range(25):
        name, screen, inputs, checks = SCENARIOS[(i + 3) % len(SCENARIOS)]
        name = f"{name} – {['happy path', 'edge case', 'negative', 'boundary', 'regression'][i % 5]}"
        if i == 24:
            name = "New TestCase"
        folders = [
            ("Precondition", [step("OpenUrl", [v("Url", "{CP[BaseUrl]}/claims")]), rtb_ref()]),
            ("Process", [step(screen, [iv if iv.find("{Click}") > 0 else iv for iv in inputs])]),
            ("Verification", [step(screen, checks)]),
            ("Postcondition", [step("Header", [v("Log out", "{Click}")])]),
        ]
        tcs.append(testcase(name, [], f"{name} – scripted with the reusable login block.",
                            f"CLM-{1600 + i}", folders=folders))
        n += 1

    assert n == 48, n
    library = (
        '<ReusableTestStepBlock Name="RTB_Login">'
        '<BusinessParameters><BusinessParameter Name="Username"/><BusinessParameter Name="Password"/></BusinessParameters>'
        + step("Login Page", [v("Username", "{PL[Username]}"), v("Password", "{PL[Password]}", dtype="Password")])
        + step("Login Page", [v("Login", "{Click}")])
        + step("Dashboard", [v("Dashboard Title.Visible", "True", "WaitOn")])
        + "</ReusableTestStepBlock>"
    )
    params = ('<TestConfigurationParameter Name="BaseUrl" Value="https://qa2.example.internal"/>'
              '<TestConfigurationParameter Name="ClaimsUser" Value="claims_member01"/>'
              '<TestConfigurationParameter Name="ClaimsPassword" Value="*****"/>')
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ToscaExport Name="Claims_Regression" ExportedFrom="Tosca Commander">'
        f'<Configuration>{params}</Configuration>'
        f'<Library>{library}</Library>'
        f'<TestCaseFolder Name="Claims">{"".join(tcs)}</TestCaseFolder>'
        '</ToscaExport>\n'
    )


def build_results(xml: str) -> str:
    import xml.etree.ElementTree as ET
    names = [tc.get("Name") for tc in ET.fromstring(xml).iter("TestCase")]
    failed = {"Submit Claim", names[1], names[2], names[6], names[11], names[30], names[40]}
    not_run = {names[45], names[46]}
    rows = []
    for nm in names:
        if nm in failed:
            msg = ("Timeout waiting for control 'Confirmation Text'" if nm == "Submit Claim" else
                   "Could not resolve host qa2.example.internal" if nm in {names[2], names[6]} else
                   "Verification failed: expected value not found")
            rows.append(f'<testcase name={quoteattr(nm)} time="41.2"><failure message={quoteattr(msg)}/></testcase>')
        elif nm in not_run:
            rows.append(f'<testcase name={quoteattr(nm)} time="0"><skipped message="Not executed"/></testcase>')
        else:
            rows.append(f'<testcase name={quoteattr(nm)} time="{random.randint(18, 70)}.{random.randint(0, 9)}"/>')
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            f'<testsuites><testsuite name="Claims nightly run" tests="{len(names)}">{"".join(rows)}</testsuite></testsuites>\n')


JIRA_ISSUE = {
    "key": "CLM-1482",
    "type": "Test",
    "status": "In test",
    "summary": "Member submits a medical claim with supporting document",
    "acceptance_criteria": [
        "Member can submit a claim with diagnosis and amount",
        "Member details auto-fill from member ID",
        "A supporting document can be attached",
        "New claims show status \"Pending review\"",
    ],
    "steps": [
        {"action": "Log in as a claims member", "expected": "Member dashboard is shown"},
        {"action": "Open \"New claim\"", "expected": "Empty claim form is displayed"},
        {"action": "Enter member ID M-10023", "expected": "Member name fills in automatically"},
        {"action": "Enter diagnosis code and amount", "expected": "Values are accepted without errors"},
        {"action": "Upload a supporting document", "expected": "File name shows under Attachments"},
        {"action": "Submit the claim", "expected": "Confirmation with a claim number"},
        {"action": "Check claim status", "expected": "Status is \"Pending review\""},
    ],
}


if __name__ == "__main__":
    xml = build_workspace()
    (OUT / "Claims_Regression.xml").write_text(xml, encoding="utf-8")
    (OUT / "Claims_Run.xml").write_text(build_results(xml), encoding="utf-8")
    (OUT / "CLM-1482.json").write_text(json.dumps(JIRA_ISSUE, indent=2), encoding="utf-8")
    print("wrote", [p.name for p in OUT.glob("*.xml")], "CLM-1482.json")
