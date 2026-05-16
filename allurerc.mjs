import { env } from "node:process";

const reportName = env.ALLURE_REPORT_NAME || "KnightSpiral Quality Report";
const reportLanguage = env.ALLURE_REPORT_LANGUAGE || "en";
const localRunId = env.ALLURE_RUN_ID || new Date().toISOString();

export default {
  name: reportName,
  output: env.ALLURE_OUTPUT || "./reports/allure-report",
  historyPath: env.ALLURE_HISTORY_PATH || "./reports/allure-history/history.jsonl",
  appendHistory: true,
  knownIssuesPath: env.ALLURE_KNOWN_ISSUES_PATH || "./allure/known.json",
  variables: {
    Project: "knightspiral",
    Runtime: "pytest",
    Language: "Python",
    "Run ID": localRunId,
    Branch: env.GITHUB_REF_NAME || env.BRANCH_NAME || env.ALLURE_BRANCH || "local",
    Commit: env.GITHUB_SHA || env.GIT_COMMIT || env.ALLURE_COMMIT || "local",
    "Coverage HTML": "reports/coverage-html/index.html",
    "Coverage XML": "reports/coverage.xml",
    "Benchmark JSON": "reports/benchmark.json"
  },
  defaultLabels: {
    owner: "DJ Stomp",
    layer: "python",
    package: "knightspiral"
  },
  environments: {
    local: {
      name: "Local",
      matcher: ({ labels }) => labels.some(({ name, value }) => name === "environment" && value === "local"),
      variables: {
        Runner: "local",
        Project: "knightspiral"
      }
    },
    github: {
      name: "GitHub Actions",
      matcher: ({ labels }) => labels.some(({ name, value }) => name === "environment" && value === "github"),
      variables: {
        Runner: "github-actions",
        Repository: env.GITHUB_REPOSITORY || "unknown"
      }
    }
  },
  categories: {
    rules: [
      {
        name: "Performance regressions",
        id: "performance-regressions",
        matchers: {
          statuses: ["failed", "broken"],
          labels: { suite: "benchmarks" },
          message: "benchmark"
        },
        groupBy: ["status", "severity"],
        groupByMessage: true,
        expand: true
      },
      {
        name: "Coverage failures",
        id: "coverage-failures",
        matchers: {
          statuses: ["failed", "broken"],
          message: "coverage|cov|Coverage"
        },
        groupBy: ["status"],
        groupByMessage: true,
        expand: true
      },
      {
        name: "CLI contract failures",
        id: "cli-contract-failures",
        matchers: {
          statuses: ["failed", "broken"],
          labels: { feature: "CLI" }
        },
        groupBy: ["status"],
        groupByMessage: true,
        expand: true
      },
      {
        name: "Simulation logic failures",
        id: "simulation-logic-failures",
        matchers: {
          statuses: ["failed", "broken"],
          labels: { feature: "Simulation" }
        },
        groupBy: ["status"],
        groupByMessage: true,
        expand: true
      },
      {
        name: "New or regressed failures",
        id: "new-or-regressed-failures",
        matchers: {
          statuses: ["failed", "broken"],
          transitions: ["new", "regressed", "malfunctioned"]
        },
        groupBy: ["transition", "status"],
        groupByMessage: true,
        groupEnvironments: true,
        expand: true
      },
      {
        name: "Flaky failures",
        id: "flaky-failures",
        matchers: {
          statuses: ["failed", "broken"],
          flaky: true
        },
        groupBy: ["flaky", "status"],
        groupByMessage: true,
        expand: true
      },
      {
        name: "Broken test harness",
        id: "broken-test-harness",
        matchers: {
          statuses: ["broken"]
        },
        groupBy: ["status"],
        groupByMessage: true,
        expand: true
      },
      {
        name: "Product failures",
        id: "product-failures",
        matchers: {
          statuses: ["failed"]
        },
        groupBy: ["severity", "status"],
        groupByMessage: true,
        expand: false
      }
    ]
  },
  qualityGate: {
    rules: [
      {
        maxFailures: 0,
        fastFail: false
      }
    ]
  },
  plugins: {
    awesome: {
      options: {
        reportName,
        reportLanguage,
        singleFile: false,
        open: false,
        publish: false
      }
    },
    dashboard: {
      options: {
        reportName: `${reportName} Dashboard`,
        reportLanguage,
        singleFile: false
      }
    },
    classic: {
      options: {
        reportName: `${reportName} Classic`,
        reportLanguage,
        singleFile: false
      }
    },
    csv: {
      options: {
        fileName: "allure-report.csv"
      }
    },
    log: {
      options: {
        groupBy: "none"
      }
    }
  }
};
