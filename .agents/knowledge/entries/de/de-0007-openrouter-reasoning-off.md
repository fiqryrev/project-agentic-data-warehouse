---
id: de-0007
title: OpenRouter turns reasoning off with reasoning.enabled, not chat_template_kwargs
tags: [openrouter, nvidia, reasoning, thinking, gateway, litellm, alias, non-reasoning]
paths: [infra/llm-gateway/config.yaml]
status: active
created: 2026-11-22
last_verified: 2026-11-22
evidence:
  - "infra/llm-gateway/config.yaml::OpenRouter ignores chat_template_kwargs"
  - docs/task-management/32-provider-comparison.md::148 reasoning tokens
supersedes: []
---

## Rule

A non-reasoning alias on OpenRouter sets `extra_body: {reasoning: {enabled: false}}`; on NVIDIA
it sets `extra_body: {chat_template_kwargs: {enable_thinking: false}}`. Check the alias with a
one-word prompt and read `completion_tokens_details.reasoning_tokens`: it must be 0.

## Why

The same model on two providers takes different switches. With NVIDIA's switch, OpenRouter still
reasoned (148 reasoning tokens for "pong", M12); a comparison of providers would have compared a
reasoning model with a non-reasoning one.

## How to apply

When adding an alias for another provider, find that provider's reasoning switch, then measure
both aliases of a pair with the same prompt before comparing them (`make compare-providers`).

## Example

`openai/adw-non-reasoning` (NVIDIA) and `openai/adw-or-non-reasoning` (OpenRouter) both return
"pong" with 3 completion tokens and 0 reasoning tokens.
