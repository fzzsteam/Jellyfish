# Project Workbench Tab Stats Design

## Goal

Move lightweight project progress signals into the Project Workbench tab header so the main tab content stays focused on its own table or asset list.

## Current Problem

The chapter list currently has a large summary block above the table. It mixes two different concerns:

- chapter progress, which belongs to the chapter workflow
- asset health, which belongs to asset management

Because the block is visually large but contains only a few numbers, the page feels unbalanced. It also makes the chapter tab look responsible for asset health.

## Approved Direction

Use the existing sticky tab header as the home for lightweight statistics.

- The chapter tab should expose chapter progress in or near the tab label.
- Asset tabs should expose their own asset health counts in or near their tab labels.
- The chapter list content should return to a focused table area with create/edit/enter actions.

## UI Design

The tab label remains compact and scannable:

- `章节` can show chapter workflow counts such as pending confirmation and ready counts.
- `角色`, `场景`, `道具`, and `服装` can show generated/total health counts for that asset category.
- The count style should be subtle and secondary, not a separate card.

The tab header is sticky, so these numbers remain visible while the user works inside a tab.

## Responsibilities

The chapter tab owns chapter workflow status:

- incomplete chapters
- pending shot confirmations
- ready shots
- generating shots when useful

Asset tabs own asset health:

- total linked project assets in that category
- assets with a usable generated image or thumbnail

The chapter list should not display cross-category asset health.

## Data Flow

Reuse the existing OpenAPI generated clients.

- Chapter flow counts can continue to use existing chapter flow stat loading.
- Asset health can continue to use the project entity link APIs already used by asset tabs.
- No new backend API is required for this layout adjustment.

## Testing

Frontend validation must run:

```bash
pnpm exec tsc --noEmit
```

No OpenAPI update is required because this design does not change backend API contracts.
