
import time
from loguru import logger

try:
    from pynput import keyboard
    from whisperbridge.utils.keyboard_utils import KeyboardUtils
except ImportError as e:
    print(f"Error: {e}")
    print("Ensure dependencies are installed: pip install pynput loguru")
    import sys
    sys.exit(1)

def run_interactive_test():
    print("Starting CUSTOM VK-ONLY HotKey detector...")
    
    # VK Codes for Windows:
    # CTRL: 17, ALT: 18, J: 74
    TARGET_VKS = {17, 18, 74}
    
    class VKDetector:
        def __init__(self, target_vks, callback):
            self.target_vks = set(target_vks)
            self.current_vks = set()
            self.callback = callback
            self.triggered = False

        def on_event(self, vk, is_press):
            if vk == 'N/A': return
            
            try:
                vk_int = int(vk)
            except ValueError:
                # Handle cases where VK is a string like '162' (Ctrl)
                return

            if is_press:
                self.current_vks.add(vk_int)
                # Check if all targets are in current
                if self.target_vks.issubset(self.current_vks):
                    if not self.triggered:
                        self.callback()
                        self.triggered = True
            else:
                self.current_vks.discard(vk_int)
                if not self.target_vks.issubset(self.current_vks):
                    self.triggered = False

    def on_success():
        print(f"\n🔥 [SUCCESS!!!] Custom VK-Only Detector TRIGGERED! 🔥\n")

    # Map pynput keys to Windows VK codes manually for this test
    # (In the real app, we'll do this automatically)
    def get_vk(key):
        # 1. Try to get vk from attribute
        vk = getattr(key, 'vk', None)
        if vk is not None: return vk
        
        # 2. Hardcoded mapping for modifiers if VK is missing
        name = str(key)
        if 'ctrl' in name: return 17
        if 'alt' in name: return 18
        if 'shift' in name: return 16
        return None

    detector = VKDetector(TARGET_VKS, on_success)

    def on_press(key):
        vk = get_vk(key)
        detector.on_event(vk, True)
        print(f"[PRESS] {str(key):<20} | VK: {str(vk):<5} | Active VKS: {detector.current_vks}")

    def on_release(key):
        vk = get_vk(key)
        detector.on_event(vk, False)
        
        if key == keyboard.Key.esc:
            return False

    # Start the listener
    try:
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            print(f"VK-Only Detector ACTIVE for VKS: {TARGET_VKS} (Ctrl+Alt+J)")
            listener.join()
    except Exception as e:
        print(f"Listener error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_interactive_test()
