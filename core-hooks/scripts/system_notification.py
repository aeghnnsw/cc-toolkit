#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# dependencies = [
#   "chime",
# ]
# ///

import sys
import platform
import glob as globmod


def has_audio_output():
    """Check if the system has audio output devices available."""
    system = platform.system()
    if system == "Darwin":
        return True
    if system == "Linux":
        # Check for PCM playback devices in /dev/snd/
        return len(globmod.glob("/dev/snd/pcm*p*")) > 0
    # Unknown platform, assume audio is available
    return True


def play_notification_sound(sound_type="default"):
    """
    Play notification sound using chime package with material theme.

    Args:
        sound_type: Type of sound to play (success, error, info, attention, default)
    """
    if not has_audio_output():
        return

    try:
        import chime

        # Set theme to material
        chime.theme('material')

        # Play different sounds based on type - use sync=True to avoid hanging
        if sound_type == "success":
            chime.success(sync=True)
        elif sound_type == "error":
            chime.error(sync=True)
        elif sound_type == "info":
            chime.info(sync=True)
        elif sound_type == "attention":
            chime.warning(sync=True)
        else:
            chime.warning(sync=True)  # default

    except Exception:
        pass  # Silent failure — no audio fallback


def main():
    try:
        # Check for command line arguments first
        if len(sys.argv) > 1:
            sound_type = None
            if '--success' in sys.argv:
                sound_type = 'success'
            elif '--error' in sys.argv:
                sound_type = 'error'
            elif '--info' in sys.argv:
                sound_type = 'info'
            elif '--attention' in sys.argv:
                sound_type = 'attention'

            # Play the specified sound
            if sound_type:
                play_notification_sound(sound_type)

        # No stdin processing needed for command line usage

        sys.exit(0)

    except Exception:
        # Handle any other errors gracefully
        sys.exit(0)

if __name__ == '__main__':
    main()
