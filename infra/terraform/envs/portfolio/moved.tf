# Story 6.2 moved the composition into modules/stack (see main.tf). These
# blocks re-address Story 6.1's live resources so the first 6.2 plan shows
# moves, not replacements. The hosted-zone data source needs none: data sources
# are re-read, not tracked.
moved {
  from = module.network
  to   = module.stack.module.network
}

moved {
  from = module.edge
  to   = module.stack.module.edge
}

moved {
  from = module.identity
  to   = module.stack.module.identity
}
