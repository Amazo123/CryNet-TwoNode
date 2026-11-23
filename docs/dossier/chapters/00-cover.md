<div class="cover">
<h1>CryNet</h1>
<p class="sub">Infant cry detection for a two-cot ESP32 system &mdash; the complete project dossier</p>

<p class="lede">Everything that was built, measured, decided and shipped: the research that chose the
corpora, the model that came out of it, the three firmwares, the radio protocol, the wiring, the
decision record with all eighty-seven entries, the forty-one faults and how each was diagnosed, every
measured number with the method that produced it, and the exact procedure to rebuild the whole thing
from an empty checkout.</p>

<table class="meta">
<tr><td style="width:34%"><strong>Project</strong></td><td>CryNet &mdash; two-cot infant cry monitor</td></tr>
<tr><td><strong>Repository</strong></td><td><code>C:\Users\HP\.t3\projects\fp-two-node</code></td></tr>
<tr><td><strong>Remote</strong></td><td><code>origin</code> &rarr; <code>https://github.com/Amazo123/CryNet-TwoNode.git</code></td></tr>
<tr><td><strong>Head at time of writing</strong></td><td><code>0a82711</code> + D-86 port, on <code>feature/wearable-multi-cot-d86</code></td></tr>
<tr><td><strong>System</strong></td><td>2 &times; ESP32-C3 Pro Mini cot nodes &rarr; ESP32-S3 hub &rarr; ESP32-C3 SuperMini wearable</td></tr>
<tr><td><strong>Dates</strong></td><td>2026-10-28 &rarr; 2026-11-23</td></tr>
<tr><td><strong>Status</strong></td><td>Four boards verified on the bench; battery runtime unmeasured</td></tr>
<tr><td><strong>Audience</strong></td><td>A reader who must defend every decision and rebuild the system unaided</td></tr>
</table>

<h2 class="no-break">What this document is</h2>

<p>This is not a summary. It is the whole project, laid out in the order a defence would need it:
what the system is, why it is built that way, how every number was obtained, what broke, how it was
found, what was decided, and exactly what to type to reproduce any of it.</p>

<p>It is written to be <em>defensible</em>. Every claim carries its evidence &mdash; a file, a line, a
log, a commit, a measurement &mdash; so that any statement here can be checked rather than believed.
Where the project does not know something, this document says so; the open items are in
<a href="#chapter-18">Chapter 18</a>, and they are the honest state of the work, not omissions.</p>

<h2 class="no-break">How it was made</h2>

<p>The body of this dossier was assembled from the repository itself: <code>DECISIONS.md</code>
(every decision and every issue, with the reasoning), <code>PROJECT_HANDOFF.md</code> (the frozen
contracts and the file map), <code>SYSTEM_UPDATE.md</code> (the living status log, rewritten after
every change), <code>SYSTEM_WIRING.md</code> and <code>HARDWARE_COMPONENTS.md</code> (the hardware
and its power chain), <code>DEMO_RUNBOOK.md</code> (the bench procedure), the two flashing guides
(the offline route needs no toolchain at all), and the source of the three firmwares and the research
pipeline. The full text of the first-party source is reproduced in <a href="#appendix-b">Appendix B</a>
so that the claims can be checked against the code, not against this prose.</p>

<h2 class="no-break">Conventions</h2>

<ul>
<li><strong>D-n</strong> &mdash; a decision, with its rationale. <strong>I-n</strong> &mdash; an issue:
what it looked like, how it was diagnosed, what was done, what happened. <strong>O-n</strong> &mdash; an
open item. These identifiers are the project's own, from <code>DECISIONS.md</code>.</li>
<li>File references are <code>path:line</code>; quoted log lines are verbatim.</li>
<li>Where a figure is a projection rather than a measurement, it says <em>projected</em>. That
distinction is preserved throughout.</li>
<li>Two quirks in the record are worth knowing before a defence: <strong>D-51</strong> and
<strong>D-52</strong> were each used twice, and <strong>D-70</strong> was skipped, so eighty-seven
decision rows carry eighty-five distinct numbers. Both are in <a href="#chapter-18">Chapter 18</a>;
neither is a missing decision.</li>
</ul>

<p style="margin-top:8pt" class="small">Generated from the repository at <code>0a82711</code> plus the
D-86 port, on branch <code>feature/wearable-multi-cot-d86</code>.
Rebuild with <code>python docs/dossier/build.py</code>.</p>
</div>