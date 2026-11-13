# ECE6420 Zotero connection

The workspace connects **Zotero > My Library > ⭐즐겨찾기 > ECE6420 Wireless IC Design**, collection `8J2MG92V`, and its descendants. The Favorites parent is `4HKWATSR`. Collection identity was retrieved from the running Zotero Local API; it is not inferred from a similar name elsewhere in the library.

Review requests follow [Zotero Paper Review Common Prompt](../../prompt/Zotero%20Paper%20Review%20Common%20Prompt.md). This setup links the collection and preserves current reading material. It does not initiate a review of every imported document. Course handouts, homework, solutions, and textbook chapter attachments are distinct source assets; their attachment count does not imply obsolete review versions.

## Open and refresh

Keep Zotero Desktop open. Start the background mirror and open the collection index in VS Code:

```sh
./tools/open-vscode.sh
```

[Browse the collection](papers/README.md). Each item has a stable folder and a README with PDF links and a Zotero item link. Standalone handout PDFs are included. Multiple source attachments retain distinct title-based role suffixes. New local copies use `YYYY-MM-DD_HH-mm-ss_PaperTitle_Role.pdf` in `America/New_York`. Annotation autosaves keep the current filename; unchanged polling does not create versions.

```sh
./tools/zotero-project.sh status
./tools/zotero-project.sh pull-papers
./tools/start-zotero-collection-sync.sh --start
./tools/start-zotero-collection-sync.sh --status
./tools/start-zotero-collection-sync.sh --stop
```

The watcher waits five seconds after each completed cycle. Processing time is additional. It discovers new collection items and PDFs, reads saved native annotations, and replaces only mirrors that match their accepted baseline. A viewer may need to reload a PDF after replacement. Missing cloud files must first be opened/downloaded through Zotero Desktop; the Local API exposes available local files.

Equivalent **Zotero:** tasks are available through VS Code's **Terminal > Run Task** menu. Startup is explicit through the launcher or Start task; no global login item or preference is installed.

## Directions and limits

| Direction | Available behavior |
| --- | --- |
| Zotero Reader to local PDF | Automatic collection pull, including supported native annotations and handwriting. |
| Assistant to local review candidate | Scoped annotation/page reads and candidate preparation are available. |
| Local PDF or answer to Zotero Reader | Explicit, scoped publication using the project's approved private Local API authorization; verify each transaction. Local edits do not upload automatically. |

Native annotations remain editable in their existing Zotero attachments. The displayed local PDF includes copies for visibility. Editing that exported PDF does not by itself save comments back to Zotero. The project tools never modify the live Zotero database or managed storage files.

When a later review needs publication, first inspect the current attachment and supported operations. Configure a separately scoped, authorized publishing operation, preserve its identity and native annotation coordinates, and verify read-back before claiming publication. The prompt's original/latest/previous policy applies to verified review versions of the same source; do not delete different textbook chapters, lecture notes, homework, or solutions as versions. The background mirror never deletes local files or Zotero records.

## Resume and Codex access

The [project MCP configuration](../../.codex/config.toml) enables status, search, item metadata, annotation reads, PDF page reads, and candidate preparation for this collection. The [official MCP configuration documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) describes project-scoped settings. A session started before this configuration was added may need to reconnect its MCP server; the CLI is usable immediately.

```sh
./tools/zotero-project.sh search 'Noise'
./tools/zotero-project.sh annotations G3VPPK85
./tools/zotero-project.sh read G3VPPK85 --page 1
```

Identifiers are retrieved automatically. `.local/zotero/collection-sync.json` holds collection identity, server identity, item metadata, attachment versions, annotation snapshots, local paths, fingerprints, accepted PDF hashes, and conflicts. Private source bodies stay under `.local/zotero/source-bodies/` when needed. Generated state, caches, and logs are ignored by Git. `docs/zotero/papers/README.md` and per-item indexes expose the files for reading.

The installed Python runtime is reused through `.local/venvs/zotero-mcp`, which points to `/Users/jeonsang-eon/TWC-OCDM-MA-CFOest/.local/venvs/zotero-mcp`. No packages or global settings are changed. Launchers keep caches and temporary files inside this workspace. That existing runtime must remain available; `tools/zotero-requirements.lock.txt` records its dependency versions for reproducibility.

Local edits or removals of an accepted mirror cause a conflict and are preserved. Do not delete `.local/zotero/collection-sync.json` to force a refresh. Read the status, preserve the local edit, and reconcile the source/version difference before replacing anything.

## Initial verification

The initial collection pull verified 11 items, 21 original PDF attachments, and 608 native annotations, including handwriting. After the separately requested Chapter 14 link publication, the collection contains 22 available PDFs and 612 native annotations across original and latest versions. There are no missing PDFs, conflicts, or unsupported-annotation warnings. The five focused mirror tests pass, and an actual MCP stdio initialization/tool/status call verified collection 8J2MG92V. Git ignores both docs/zotero/papers/ and .local/.


## Razavi 2017: Chapter 14 navigation

Only Chapter 14, printed pages **576-606** (physical PDF pages **595-625**), was processed. No answers were added. Other chapters and other books retain their existing navigation.

- [Current displayed PDF and retained original](papers/Razavi_2017_Design_of_analog_CMOS_integrated_circuits_XEVWM2L3/README.md).
- [Open the current editable reviewed Reader](zotero://open-pdf/library/items/DSERUMML?page=595).
- Existing book item: `XEVWM2L3`; immutable original attachment: `S3G7I8KI`; latest linked Reader: `DSERUMML`.

The reviewed derivative adds **147 internal links**: 91 figure links, 26 equation links, 22 chapter-link rectangles, 5 literature citations, and one each for a section, example, and table. The book retains all 801 pages, 344 bookmarks, page labels, and its original 315 links, for 462 links total. Only link sources in Chapter 14 were added; some verified references lead to existing material in earlier chapters.

The original attachment and managed PDF were preserved. The derivative was attached through Zotero's native **Attach Link to File** command, and its four preserved highlights were imported through **File > Import Annotations**. Their original text, exact colors, and positions were verified after import; the new native keys are recorded automatically. A supported native color edit confirmed editability. The Reader body has zero embedded annotations. Every page's decoded content streams and every link were compared after native import. A Reader click on Fig. 14.6 from printed page 580 reached printed page 579. Hover previews could not be independently tested with the available UI controls.

The collection poller now owns this Reader's annotated mirror. `.local/zotero/reader-sync.json`, `sync-state.json`, `paper-retention.json`, and `ch14-review/publication.json` retain its actual IDs, native annotation snapshots, original/latest roles, accepted hashes, and publication checks. There is no previous verified review yet, so this paper has only the original and latest user-facing PDFs and the matching two active Zotero attachments. The private Reader backs the latest attachment and is not an additional attachment/version. Superseded unreviewed mirror/technical copies were removed after verification.

The native UI publication was explicitly performed for this link-only task. The MCP/CLI remain library-read-only; no general API write key or automatic local-to-Zotero publisher was added. Automatic mirroring covers saved native Reader edits. Future structural edits require a separate verified candidate and supported publication operation.

Four malformed printed problem references were preserved without speculative links:

| Printed page | Unresolved text |
| --- | --- |
| 598 | Problem 14.14.1 |
| 605 | Problem 14.14.5 (two occurrences) |
| 605 | Problem 14.14.12 |

`tools/build-razavi-ch14-links.py` retains the scoped link-building and verification logic. It creates an unpublished candidate only when explicitly run; it does not publish or edit other books. Exact link/source/target records and unresolved locations are retained in ignored `.local/zotero/ch14-review/links-manifest.json`.


## LN page repair: 2026-11-09T04:30:43-05:00

Applied five blue instructions on the original 62-page LN. Swapped original pages 32 and 33; removed original pages 24, 34, 48, and 54. The result has 58 pages. All surviving page content streams, raster-image bytes, dimensions, and rotations were preserved. No OCR, new answers, or navigation repair was requested in this batch.

The current attachment remains `26RQUBTJ` under `DDNV6RWP`. Its surviving instruction note `9X3PK25Q` retains its identity, color, and geometry, with the page index remapped and an English applied-status comment. All original instruction wording and versions are preserved in the automatic plan and in the native annotations of the retained original attachment `UPJK5MI8`. Instructions on the four removed pages were soft-deleted only after the original and its annotations were retained. No previous verified review exists yet.

The distinct 147-page source attachment `XU3XJ2T5` remains active and mirrored; it is not an obsolete version of the 62/58-page annotated LN. The book review and its Reader configuration were unchanged. The [LN index](papers/Project_undated_ECE6420_LN_Wireless_IC_DDNV6RWP/README.md) links the current 58-page review and retained original.

This transaction used the supported Zotero Local API file-upload and annotation-write operations. Its helper and complete source/version/page map are private in `.local/zotero/review-work/DDNV6RWP/2026-11-09_04-30-43_LN_Page_Repair`. A local write authorization, if remembered, stays in ignored `.local/zotero/ln-page-repair-auth.json` with mode 0600. It is not exposed in the project MCP configuration. The collection poller continues to perform reads only; local PDF edits do not publish automatically.


## Razavi 2012: Chapters 1-6 navigation (2026-11-12T17:39:32-05:00)

The reviewed RF microelectronics PDF adds **1,881 genuine internal links** originating in Chapters 1-6 (printed pages 1-428, physical pages 26-453) and their printed contents entries. The links cover 275 equation references, 1,079 figure/panel anchors, 75 section/subsection references, 132 contents-row rectangles, 148 chapter anchors, 39 example anchors, 129 chapter-scoped literature citation anchors, and four table anchors. The 131 existing chapter/section/subsection/reference/problem bookmarks in scope now land at their actual headings. All 314 bookmark titles and their hierarchy remain intact. No unresolved requested references remain in the verified plan.

All 946 page bodies, image streams, page labels, rotations, and dimensions were preserved. Ten representative rendered pages are pixel-identical to the source. Link borders have zero width. The source contains legacy GoTo actions with null destinations; those original objects are preserved, while the new links use verified explicit PDF destinations. Other chapters' source links and bookmark destinations are unchanged. Existing green questions and personal highlights were preserved; this was a navigation-only request.

The existing managed attachment remains `X5RDQG68` under the same book item `5XLCGB2J`, and its eight native annotation keys, content, colors, and positions are unchanged. The immutable original is retained as linked attachment `J83BW6HU` with eight matching editable native annotation snapshots. There was no earlier verified review to retain. The paper's [index](papers/Razavi_2012_RF_microelectronics_5XLCGB2J/README.md) links the original and current displayed PDF; [open the reviewed Reader](zotero://open-pdf/library/items/X5RDQG68?page=32).

The scoped helper used supported Local API item and managed-file upload operations with source MD5, individual item versions, fresh annotation fingerprints, and post-write read-back checks. It reused this project's existing persistent authorization in the ignored mode-0600 private store. No additional access or general MCP write tool was enabled. Automatic mirroring was restarted and reports healthy. Private original/latest role metadata and the complete link/target/version plan are in `.local/zotero/paper-retention.json` and `.local/zotero/review-work/5XLCGB2J/ch1-6-navigation/plan.json`. Superseded source/mirror/candidate technical copies were removed after verification.

`tools/build-rf-ch1-6-links.py` reproduces the scoped candidate and its structural, text-target, bookmark-coordinate, and visual checks from the accepted baseline. The publisher and finalizer are retained privately with the transaction. Re-discover and reconcile current source hashes and annotations before any further edit.

Reader click verification: Eq. (2.36) moved from printed page 20 to 19; Fig. 2.13 moved from 19 to 20; the printed contents entry for subsection 6.3.2 moved from x to 377. Hover previews could not be independently tested with the available computer-use actions.
