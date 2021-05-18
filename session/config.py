"""Configuration for IntelMQ Manager
SPDX-FileCopyrightText: 2020 Intevation GmbH <https://intevation.de>
SPDX-License-Identifier: AGPL-3.0-or-later
Funding: of initial version by SUNET
Author(s):
  * Raimund Renkert <raimund.renkert@intevation.de>
"""

from typing import List, Optional
import json
from pathlib import Path

class Config:

    """Configuration settings for IntelMQ Fody Sessions"""

    session_store: Optional[Path] = None

    session_duration: int = 24 * 3600

    def __init__(self, filename: Optional[str]):
        """Load configuration from JSON file"""
        raw = {}
        config = False

        configfiles = [
            Path('/etc/intelmq/fody-session.conf'),
            Path(__file__).parent.parent / 'etc/intelmq/fody-session.conf'
        ]

        if filename:
            configfiles.insert(0, Path(filename).resolve())

        for path in configfiles:
            if path.exists() and path.is_file():
                print(f"Loading config from {path}")
                config = True
                with path.open() as f:
                    try:
                        raw = json.load(f)
                    except json.decoder.JSONDecodeError:
                        print(f"{path} did not contain valid JSON. Using default values.")
                break
        if not config:
            print("Was not able to load a configfile. Using default values.")

        if "session_store" in raw:
            self.session_store = Path(raw["session_store"])

        if "session_duration" in raw:
            self.session_duration = int(raw["session_duration"])
