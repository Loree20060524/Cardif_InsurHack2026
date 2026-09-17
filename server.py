#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backward-compatible command-line entry point for RegIntel."""

from regintel.web import Handler, main

__all__ = ["Handler", "main"]


if __name__ == "__main__":
    main()
