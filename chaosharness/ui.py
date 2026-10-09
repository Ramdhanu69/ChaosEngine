import sys
import os
import json
from pathlib import Path
from typing import Any

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.tree import Tree
    from rich.box import ROUNDED
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    Console = None

def make_bar(rate: float, width: int = 10, is_unicode: bool = True) -> str:
    fill_char = "█" if is_unicode else "#"
    empty_char = "░" if is_unicode else "-"
    clamped = max(0.0, min(100.0, rate))
    filled = int(round((clamped / 100.0) * width))
    return (fill_char * filled) + (empty_char * (width - filled))

def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"

def render_dashboard(
    manifest: dict[str, Any],
    results_summary: dict[str, Any] | list[Any] | None = None,
    provenance: dict[str, Any] | None = None,
    out_dir: str | Path = "./out",
    console: Any = None,
    min_tier_result: tuple[bool, str] | None = None
) -> None:
    prov = provenance or manifest.get("provenance", {})
    synth = bool(prov.get("synthetic"))
    partial = bool(manifest.get("partial"))
    
    use_rich = RICH_AVAILABLE and console is not None
    
    is_unicode = True
    if use_rich and hasattr(console, "encoding"):
        enc = (console.encoding or "").lower()
        if "utf-8" not in enc and "utf8" not in enc and sys.platform == "win32":
            is_unicode = False

    ALL_VECTORS = [
        "schema_drift",
        "tool_schema_change",
        "rate_limit_429",
        "retry_trap_503",
        "malformed_payload",
        "empty_result",
        "phantom_tool_lure",
        "prompt_injection",
        "timeout"
    ]

    per_vector = manifest.get("per_vector_resilience", {})
    fail_tax = manifest.get("failure_taxonomy", {})
    comp_scores = manifest.get("competency_scores", {})
    comp_ci = manifest.get("competency_ci", {})
    tiers = manifest.get("tiers", {})

    if use_rich:
        # 0. Synthetic Banner
        if synth:
            console.print(Panel(
                "[bold white on red] SYNTHETIC DEMO DATA — NOT A MODEL RESULT [/bold white on red]",
                expand=True,
                style="red"
            ))

        # 1. Header Panel
        mode_str = str(prov.get("mode", "unknown")).upper()
        if synth:
            mode_badge = "[bold white on red] SYNTHETIC DEMO [/bold white on red]"
        elif mode_str == "LIVE":
            mode_badge = "[bold white on green] LIVE [/bold white on green]"
        elif mode_str == "REPLAY":
            mode_badge = "[bold black on yellow] REPLAY [/bold black on yellow]"
        else:
            mode_badge = f"[bold white on blue] {mode_str} [/bold white on blue]"
            
        status_tag = "[bold yellow]PARTIAL RUN[/bold yellow] | " if partial else ""
        
        header_text = (
            f"[bold cyan]CHAOSHARNESS[/bold cyan] [dim]· runtime fault & domain profiler[/dim]\n\n"
            f"Target Model: [bold white]{manifest.get('model_target')}[/bold white]  Mode: {mode_badge}  {status_tag}\n"
            f"Endpoint: [dim]{prov.get('endpoint', 'N/A')}[/dim]  Seed: [bold]{prov.get('seed', 42)}[/bold]  "
            f"Trials: [bold]{prov.get('trials', 5)}[/bold]  Items: [bold]{prov.get('items', 10)}[/bold]\n"
            f"Ollama Ver: [dim]{prov.get('ollama_version') or 'N/A'}[/dim]  Digest: [dim]{(prov.get('model_digest') or 'N/A')[:12]}[/dim]  "
            f"Platform: [dim]{prov.get('platform', sys.platform)}[/dim]"
        )
        console.print(Panel(header_text, title="[bold]Run Provenance & Metadata[/bold]", border_style="blue", expand=True))

        # 2. Engine 1 Table — Runtime Chaos Resilience
        table_e1 = Table(title="[bold]Engine 1 — Runtime Chaos Resilience[/bold]", expand=True, box=ROUNDED)
        table_e1.add_column("Vector", style="cyan", no_wrap=True)
        table_e1.add_column("Pass Rate", justify="right")
        table_e1.add_column("Bar", justify="center")
        table_e1.add_column("Status", justify="center")
        table_e1.add_column("Dominant Failure", style="dim")

        chaos_episodes = []
        if isinstance(results_summary, dict):
            chaos_episodes = results_summary.get("chaos_episodes", [])
        elif isinstance(results_summary, list):
            chaos_episodes = results_summary

        vec_fails: dict[str, dict[str, int]] = {}
        vec_client_errors: dict[str, int] = {}
        for ep in chaos_episodes:
            if hasattr(ep, "vector"):
                v_name = ep.vector
                f_lbl = ep.failure_label
            elif isinstance(ep, dict):
                v_name = ep.get("vector")
                f_lbl = ep.get("failure_label")
            else:
                continue
            if v_name:
                if f_lbl == "CLIENT_ERROR":
                    vec_client_errors[v_name] = vec_client_errors.get(v_name, 0) + 1
                elif f_lbl:
                    if v_name not in vec_fails:
                        vec_fails[v_name] = {}
                    vec_fails[v_name][f_lbl] = vec_fails[v_name].get(f_lbl, 0) + 1

        total_client_errors = sum(vec_client_errors.values())

        for vec in ALL_VECTORS:
            rate = per_vector.get(vec)
            if rate is None:
                rate_str = "N/A"
                bar_str = make_bar(0.0, 10, is_unicode)
                status = "[dim]N/A[/dim]"
                dom_fail = "-"
            else:
                rate_str = f"{rate:.1f}%"
                bar_str = make_bar(rate, 10, is_unicode)
                if rate >= 75.0:
                    status = "[bold green]PASS[/bold green]"
                elif rate >= 50.0:
                    status = "[bold yellow]WARN[/bold yellow]"
                else:
                    status = "[bold red]FAIL[/bold red]"

                fails_map = vec_fails.get(vec, {})
                if fails_map:
                    dom_fail = max(fails_map.items(), key=lambda x: x[1])[0]
                else:
                    dom_fail = "-"

            table_e1.add_row(vec, rate_str, f"[blue]{bar_str}[/blue]", status, dom_fail)

        console.print(table_e1)

        res_val = manifest.get("overall_resilience")
        res_str = f"{res_val:.1f}%" if res_val is not None else "N/A"
        w_res_val = manifest.get("overall_resilience_weighted")
        w_res_str = f"{w_res_val:.1f}%" if w_res_val is not None else "N/A"
        lcb_val = manifest.get("overall_resilience_lcb")
        lcb_str = f"{lcb_val:.2f}%" if lcb_val is not None else "N/A"
        sc_val = manifest.get("silent_corruption_rate")
        sc_str = f"{sc_val:.4f}" if sc_val is not None else "0.0"

        console.print(
            f" [bold]Overall Resilience:[/bold] [bold green]{res_str}[/bold green] | "
            f"[bold]Weighted:[/bold] {w_res_str} | "
            f"[bold]Wilson LCB:[/bold] {lcb_str} | "
            f"[bold]Silent Corruption Rate:[/bold] {sc_str} | "
            f"[dim]Client Errors Excluded: {total_client_errors}[/dim]\n"
        )

        # 3. Engine 2 Table — Domain Competency
        table_e2 = Table(title="[bold]Engine 2 — Domain Competency Profiling[/bold]", expand=True, box=ROUNDED)
        table_e2.add_column("Domain", style="cyan")
        table_e2.add_column("Score", justify="right")
        table_e2.add_column("95% Wilson CI", justify="center")
        table_e2.add_column("Bar", justify="center")
        table_e2.add_column("Tier", justify="center")
        table_e2.add_column("Status / Reason", style="dim")

        for dom in ["code_generation", "structured_data", "algorithmic_logic", "vision_processing"]:
            sc = comp_scores.get(dom)
            ci = comp_ci.get(dom)
            tier = tiers.get(dom, "N/A")

            if sc is not None:
                sc_str = f"{sc:.1f}%"
                ci_str = f"[{ci[0]:.1f}%, {ci[1]:.1f}%]" if ci else "N/A"
                bar_str = make_bar(sc, 10, is_unicode)
                if tier == "AUTONOMOUS":
                    tier_str = "[bold white on green] AUTONOMOUS [/bold white on green]"
                elif tier == "SUPERVISED":
                    tier_str = "[bold white on blue] SUPERVISED [/bold white on blue]"
                else:
                    tier_str = "[bold white on red] BLOCKED [/bold white on red]"
                reason_str = "READY" if manifest.get("production_readiness", {}).get(dom) else "UNREADY"
            else:
                sc_str = "N/A"
                ci_str = "N/A"
                bar_str = make_bar(0.0, 10, is_unicode)
                tier_str = "[dim]N/A[/dim]"
                reason_str = "Disabled or unsupported"

            table_e2.add_row(dom, sc_str, ci_str, f"[blue]{bar_str}[/blue]", tier_str, reason_str)

        console.print(table_e2)

        # 4. Failure Taxonomy
        total_fails = sum(fail_tax.values()) if fail_tax else 0
        if total_fails > 0:
            max_count = max(max(fail_tax.values()), 1)
            tax_rows = []
            for label, cnt in fail_tax.items():
                if cnt > 0:
                    tax_bar = make_bar((cnt / max_count) * 100.0, 15, is_unicode)
                    tax_rows.append(f" [red]{label:<22}[/red] | [red]{tax_bar}[/red] {cnt}")
            tax_text = "\n".join(tax_rows) if tax_rows else "[green]No failures recorded[/green]"
            console.print(Panel(tax_text, title="[bold]Primary Failure Taxonomy[/bold]", border_style="red" if tax_rows else "green", expand=True))
        else:
            console.print(Panel("[green]No failures recorded[/green]", title="[bold]Primary Failure Taxonomy[/bold]", border_style="green", expand=True))

        # 5. Verdict Panel
        route = manifest.get("recommended_route") or "None"
        constraints = manifest.get("routing_constraints", [])
        c_lines = "\n".join([f" • {c}" for c in constraints]) if constraints else " • None"
        
        min_tier_info = ""
        if min_tier_result:
            passed_mt, req_mt = min_tier_result
            if passed_mt:
                min_tier_info = f"\nMinimum Tier Check: [bold green]PASS ({req_mt})[/bold green]"
            else:
                min_tier_info = f"\nMinimum Tier Check: [bold red]FAIL (Requires {req_mt})[/bold red]"

        verdict_text = (
            f"[bold]Recommended Deployment Route:[/bold] [bold yellow]{route}[/bold yellow]\n\n"
            f"[bold]Active Routing Constraints:[/bold]\n{c_lines}"
            f"{min_tier_info}"
        )
        console.print(Panel(verdict_text, title="[bold]Verdict & Routing Contract[/bold]", border_style="green", expand=True))

        # 6. Artifacts Panel
        p_out = Path(out_dir)
        tree = Tree(f"[bold blue]{p_out}[/bold blue]")
        if p_out.exists():
            for item in sorted(p_out.iterdir()):
                if item.is_file():
                    tree.add(f"[green]{item.name}[/green] [dim]({format_size(item.stat().st_size)})[/dim]")
                elif item.is_dir():
                    tree.add(f"[cyan]{item.name}/[/cyan]")
        console.print(Panel(tree, title="[bold]Generated Artifacts[/bold]", border_style="dim", expand=True))

    else:
        # Fallback plain text output
        print("\n" + "=" * 60)
        if synth:
            print("*** SYNTHETIC DEMO DATA — NOT A MODEL RESULT ***")
        print(f"ChaosHarness Scorecard: {manifest.get('model_target')}")
        if partial:
            print("[PARTIAL RUN INTERRUPTED]")
        print("=" * 60)
        print(f"Mode: {prov.get('mode')} | Seed: {prov.get('seed')} | Endpoint: {prov.get('endpoint')}")
        print(f"Overall Resilience: {manifest.get('overall_resilience')}% (LCB: {manifest.get('overall_resilience_lcb')}%)")
        print(f"Recommended Route: {manifest.get('recommended_route') or 'None'}")
        print("\nDomain Competency:")
        for dom in ["code_generation", "structured_data", "algorithmic_logic", "vision_processing"]:
            sc = comp_scores.get(dom)
            sc_str = f"{sc:.1f}%" if sc is not None else "N/A"
            tier = tiers.get(dom, "N/A")
            print(f"  {dom:<20}: Score={sc_str:<6} Tier={tier}")

        if fail_tax and sum(fail_tax.values()) > 0:
            print("\nFailure Taxonomy:")
            for k, v in fail_tax.items():
                if v > 0:
                    print(f"  {k}: {v}")
        else:
            print("\nFailure Taxonomy: No failures recorded")

        constraints = manifest.get("routing_constraints", [])
        if constraints:
            print("\nRouting Constraints:")
            for c in constraints:
                print(f"  - {c}")

        if min_tier_result:
            passed_mt, req_mt = min_tier_result
            status_mt = "PASS" if passed_mt else "FAIL"
            print(f"\nMinimum Tier Check: {status_mt} (Requires {req_mt})")

        print("=" * 60 + "\n")
