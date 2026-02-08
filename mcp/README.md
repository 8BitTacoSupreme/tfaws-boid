# MCP Server Evaluation — Phase 3

## terraform-mcp-server (thrashr888)

**Version:** Installed via npx (`@anthropics/terraform-mcp-server`)
**Purpose:** Terraform Registry API access — provider docs, module search, resource schemas.
**Verdict:** Keep. Provides capability the agent does not have natively.

### Tools Evaluated

| Tool | Query Tested | Response Quality | Useful? |
|------|-------------|-----------------|---------|
| `providerDetails` | `hashicorp/aws` | Returns versions, source URL, doc links. Fast. | Yes — version checks |
| `resourceArgumentDetails` | `aws_security_group` | Full argument schema with types, descriptions, required flags. | Yes — HCL generation |
| `resourceUsage` | `aws_instance` | Complete example HCL with common arguments. | Yes — HCL templates |
| `moduleSearch` | `vpc` | Returns top modules with download counts, descriptions. | Yes — module recommendations |
| `moduleDetails` | `terraform-aws-modules/vpc/aws` | Full inputs/outputs with types and defaults. | Yes — module usage |
| `listDataSources` | `aws` | Lists all AWS data sources with descriptions. | Marginal — agent rarely needs this |

### Gaps (filled by CLI tools in this project)

| Gap | Why MCP doesn't cover it | Our solution |
|-----|-------------------------|-------------|
| Parse `terraform plan -json` | MCP server talks to Registry API, not local CLI | `scripts/tf_plan_analyzer.py` |
| Cross-reference Canon knowledge | MCP has no awareness of our Canon data | `scripts/canon_search.py` |
| Run terraform commands | Agent already has bash; wrapping in MCP adds overhead | Direct bash via Flox env |
| LocalStack orchestration | Out of scope for registry server | Enhanced `sandbox/validate.sh` |

### Configuration

The existing `.claude/settings.json` entry is correct. No changes needed:
```json
{
  "mcpServers": {
    "terraform-registry": {
      "command": "npx",
      "args": ["-y", "@anthropics/terraform-mcp-server"]
    }
  }
}
```

## Why Not Custom MCP Servers

See `docs/ARCHITECTURE.md` — ADR "CLI Tools Over Custom MCP Servers".

**Summary:** The agent has bash access to `terraform`, `python3`, and every Flox
tool. MCP servers add value when the agent lacks a capability. For plan parsing
and Canon search, CLI scripts called via bash give the same results with:
- Zero protocol overhead
- No Node.js process to manage
- Direct debugging with `python3 script.py --help`
- Testable with standard unittest

The `terraform-mcp-server` earns its keep because it provides Registry API
access the agent wouldn't otherwise have. Our CLI tools fill the local gaps.
