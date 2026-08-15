import fs from "node:fs";
import path from "node:path";

const escapeXml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");

export default class StreamingJUnitReporter {
  startedAt = new Date();
  cases = new Map();

  printsToStdio() {
    return true;
  }

  onBegin() {
    this.startedAt = new Date();
  }

  onTestEnd(test, result) {
    this.cases.set(test.id, { test, result });
    this.writeReport();
  }

  writeReport() {
    const grouped = new Map();
    for (const recorded of this.cases.values()) {
      const file = path
        .relative(path.join(process.cwd(), "e2e"), recorded.test.location.file)
        .replaceAll("\\", "/");
      const key = `${recorded.test.parent.project()?.name ?? ""}\u0000${file}`;
      const cases = grouped.get(key) ?? [];
      cases.push(recorded);
      grouped.set(key, cases);
    }

    let total = 0;
    let failures = 0;
    let skipped = 0;
    let duration = 0;
    const suites = [];
    for (const [key, recordedCases] of grouped) {
      const [project, file] = key.split("\u0000");
      let suiteFailures = 0;
      let suiteSkipped = 0;
      let suiteDuration = 0;
      const cases = recordedCases.map(({ test, result }) => {
        const isSkipped = result.status === "skipped";
        const isFailure = !isSkipped && test.outcome() === "unexpected";
        const message = result.error?.message ?? result.errors[0]?.message ?? "";
        suiteFailures += Number(isFailure);
        suiteSkipped += Number(isSkipped);
        suiteDuration += result.duration;
        const outcome = isSkipped
          ? "<skipped/>"
          : isFailure
            ? `<failure message="${escapeXml(message)}">${escapeXml(message)}</failure>`
            : "";
        return `<testcase name="${escapeXml(test.title)}" classname="${escapeXml(file)}" time="${(
          result.duration / 1000
        ).toFixed(3)}">${outcome}</testcase>`;
      });
      total += recordedCases.length;
      failures += suiteFailures;
      skipped += suiteSkipped;
      duration += suiteDuration;
      suites.push(
        `<testsuite name="${escapeXml(file)}" timestamp="${this.startedAt.toISOString()}" hostname="${escapeXml(
          project,
        )}" tests="${recordedCases.length}" failures="${suiteFailures}" skipped="${suiteSkipped}" errors="0" time="${(
          suiteDuration / 1000
        ).toFixed(3)}">${cases.join("")}</testsuite>`,
      );
    }
    const xml = `<testsuites tests="${total}" failures="${failures}" skipped="${skipped}" errors="0" time="${(
      duration / 1000
    ).toFixed(3)}">${suites.join("")}</testsuites>\n`;
    const output = path.resolve(process.cwd(), process.env.PLAYWRIGHT_JUNIT_OUTPUT_FILE);
    fs.mkdirSync(path.dirname(output), { recursive: true });
    fs.writeFileSync(output, xml, "utf8");
  }
}
