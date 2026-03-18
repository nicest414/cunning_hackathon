from pynput import keyboard

def on_press(key):
    print(f"キーが押されました: {key}")

print("キー入力待機中... 何かキーを押してください (終了は Ctrl+C)")
with keyboard.Listener(on_press=on_press) as listener:
    listener.join()