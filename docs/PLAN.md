# terraform-aws-boid Development Plan

## Current Phase: 1 — Foundation

## North Star
A developer runs `flox activate -r floxhub/terraform-aws` and gets an
expert Terraform+AWS agent with zero setup. The agent validates its
suggestions against LocalStack before presenting them. Over time, the
agent learns the user's conventions and infrastructure quirks.

## Key Milestones
- [ ] Phase 1: Foundation (Flox env, SQLite schema, activation hooks, LocalStack)
- [ ] Phase 2: Canon Population (error sigs, AWS limits, IAM rules)
- [ ] Phase 3: MCP Servers (terraform-mcp, localstack-mcp)
- [ ] Phase 4: Memories Integration (write/read path, conventions, fork)
- [ ] Phase 5: E2E Validation (5 demo scenarios, README, publish)
