# How Amazon uses AI agents to anticipate and counter cyber threats

## Amazon's competitive-agent architecture creates a continuous improvement cycle that develops security protections at machine speed, reducing what typically takes weeks down to hours.

In cybersecurity, the battle between adversaries and defenders has reached new levels of sophistication and speed, especially with the emergence of AI. At Amazon, we've developed a groundbreaking solution: Autonomous Threat Analysis (ATA), a security system that leverages agentic AI and adversarial multiagent reinforcement learning to enhance and scale defenses, ensuring our systems remain robust against emerging threats.

The concept of ATA began in August 2024 during an internal hackathon aimed at addressing limitations in traditional security testing. Our goal was to create a system that could preemptively develop detection capabilities and rapidly adapt security controls. We developed the initial prototype in just 48 hours, demonstrating the potential of this approach by identifying a loophole in a threat detection rule and automatically generating an improved solution. This success led to the creation of ATA, the autonomous security-testing system we use today.

## How Autonomous Threat Analysis works

ATA executes comprehensive security-testing scenarios with red-team and blue-team AI agents. Red-team agents simulate adversaries’ techniques, while blue-team agents validate detection coverage and generate new or improved rules when novel techniques are found. ATA operates through a graph workflow system where each node represents a specialized AI agent with distinct capabilities and objectives. The workflow coordinates these agents in sequences, with outputs from one agent becoming inputs for the next.

The system operates in specially created environments that mimic our codebases and production systems while remaining completely isolated from actual operations and customer data. This ensures zero risk to actual operations while providing realistic testing conditions.

One of ATA's key innovations is its grounded execution architecture. Rather than relying purely on AI evaluation, ATA validates every technique and detection against real infrastructure. Red-team agents execute actual commands on test systems, producing real telemetry. Blue-team agents validate detection effectiveness (precision/recall) by querying actual log databases. If an agent claims it executed a technique, there are timestamped logs from specific hosts proving it. This design mitigates AI hallucination risks, as every claim is backed by observable evidence from actual system execution.

## Case study: Python reverse shells

Our work on Python reverse shells illustrates how this approach works in practice. Reverse shells are a common technique where adversaries establish command and control by creating a connection from a compromised system back to their server. Python-based implementations are particularly challenging to detect because Python is widely installed across infrastructure, and commands can be obfuscated in numerous ways.

To address this challenge, ATA's red-team agents systematically generated and successfully executed 37 reverse-shell-technique variations. This exploratory testing identified novel techniques that informed more-targeted analysis. Building on these findings, we conducted focused testing of our Python reverse-shell detection rule.

The system generated 64 variants of the threat and developed an improved detection rule. Testing against these variants and one hour of production audit data, the rule achieved 1.00 precision and 1.00 recall. The improvement process demonstrated consistent reproducibility across multiple independent runs. This case study uncovered additional threat-hunting opportunities and informed multiple new detection rules, demonstrating ATA's ability to systematically strengthen our defenses.

## Safeguards and responsible AI

To ensure the responsible use of AI in security testing, ATA incorporates multiple layers of safeguards. All testing occurs in isolated, ephemeral environments, and any successful technique variations are immediately converted into detection rules. Our grounded execution architecture mitigates AI hallucination risks, while rigorous validation prevents false positives, ensuring we can detect and defend against techniques before threat actors adopt them in the wild. Furthermore, strict access controls and comprehensive audit logging maintain the integrity of our systems.

Human oversight remains critical for approving changes before deployment to production. This balance between automation and human judgment allows us to leverage the strengths of AI while ensuring responsible and effective security measures.

## Strategic impact

The system demonstrates remarkable resilience. When technique executions initially fail, agents automatically analyze errors and refine their approaches, typically succeeding within three refinement attempts. This adaptive capability, combined with automated validation and detection rule generation, reduces the end-to-end workflow from weeks of manual effort down to approximately four hours, a 96% reduction in time. This efficiency not only enhances our security posture but also allows our security teams to focus on strategic initiatives rather than rote testing.

Unlike traditional security-testing tools, which execute predefined techniques, ATA allows agents to reason about their actions and adapt their strategies based on outcomes. For example, in a test involving a multistep plan including reconnaissance, exploitation, and lateral movement, ATA's agents successfully simulated the complete sequence of steps and identified two new detection opportunities in under an hour.

## Scaling security with AI

As the threat landscape evolves, ATA provides a scalable solution to keep pace. The system executes 10 to 30 technique variations concurrently, with individual detection-rule tests completing in one to three hours, depending on scope and parallelization settings. This scalability is crucial as our infrastructure and services grow in complexity.

Although ATA automates many aspects of security testing, it is designed to augment, not replace, human expertise. Human security professionals excel at creative thinking and understand business context in ways that AI cannot replicate. ATA enables these experts to focus on strategic initiatives while AI handles routine testing, creating a partnership that leverages the strengths of both.

By automating the red-/blue-team testing cycle, ATA enables us to stay ahead of adversaries, reduce false positives, and enhance our overall security posture. This is not just about efficiency; it's about protecting our customers and ensuring that our systems are resilient against the most sophisticated threats.

Tags

- [Agentic AI](https://www.amazon.science/tag/agentic-ai)

About the Author

Daniel Weiss is a senior security engineer for Amazon Security and is part of the team that developed and created Autonomous Threat Analysis (ATA).