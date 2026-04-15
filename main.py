import tkinter as tk
from tkinter import messagebox
import json
import os
import sys
import pygame
import random

class QuizApp:
    def __init__(self, root):
        self.root = root
        self.root.title("仏法研鑽クイズアプリ")
        self.root.geometry("700x600")
        self.root.configure(bg="#f0f4f8")

        # 音声の初期化 (エラー対策)
        try:
            pygame.mixer.init()
        except:
            pass
        
        self.load_data()
        self.setup_category_screen()

    def load_data(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(base_dir, "questions.json")
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                self.all_data = json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"JSON読み込み失敗: {e}")
            sys.exit()

    def clear_screen(self):
        """画面を掃除する"""
        for widget in self.root.winfo_children():
            widget.destroy()

    def setup_category_screen(self):
        """章を選択するメニュー画面"""
        self.clear_screen()
        
        tk.Label(self.root, text="研鑽したい章を選んでください", 
                 font=("MS Gothic", 20, "bold"), bg="#f0f4f8", fg="#2c3e50").pack(pady=30)
        
        container = tk.Frame(self.root, bg="#f0f4f8")
        container.pack()

        # 章ごとにボタンを作成
        for category in self.all_data.keys():
            btn = tk.Button(
                container, text=category, font=("MS Gothic", 12), 
                width=40, height=2, bg="#ffffff", relief="flat",
                cursor="hand2", command=lambda c=category: self.start_quiz(c)
            )
            btn.pack(pady=5)

    def start_quiz(self, category):
        """クイズ開始"""
        self.questions = list(self.all_data[category])
        if not self.questions:
            messagebox.showinfo("準備中", "この章の問題は現在準備中です。")
            return
            
        random.shuffle(self.questions) # ランダム出題
        self.current_index = 0
        self.score = 0
        
        self.clear_screen()
        self.setup_ui()
        self.display_question()

    def setup_ui(self):
        """クイズ画面のUI構築"""
        self.label_info = tk.Label(self.root, text="", font=("Arial", 11), bg="#f0f4f8")
        self.label_info.pack(pady=10)

        self.label_question = tk.Label(
            self.root, text="", font=("MS Gothic", 16, "bold"),
            wraplength=600, bg="white", height=6, relief="flat", padx=20
        )
        self.label_question.pack(pady=20, fill="x", padx=40)

        # 選択肢用
        self.choice_frame = tk.Frame(self.root, bg="#f0f4f8")
        self.btn_list = []
        colors = ["#3498db", "#2ecc71", "#f1c40f", "#e74c3c"]
        for i in range(4):
            btn = tk.Button(self.choice_frame, text="", font=("MS Gothic", 12),
                            width=45, height=2, bg=colors[i], fg="black",
                            command=lambda idx=i: self.check_answer(idx, "choice"))
            btn.pack(pady=5)
            self.btn_list.append(btn)

        # 記述用
        self.input_frame = tk.Frame(self.root, bg="#f0f4f8")
        self.entry_answer = tk.Entry(self.input_frame, font=("Arial", 18), width=25, justify="center")
        self.entry_answer.pack(pady=20)
        self.entry_answer.bind("<Return>", lambda e: self.check_answer(None, "input"))
        tk.Button(self.input_frame, text="回答を確定", font=("MS Gothic", 12, "bold"),
                  bg="#34495e", fg="white", width=20, height=2,
                  command=lambda: self.check_answer(None, "input")).pack()

    def display_question(self):
        """問題表示"""
        if self.current_index < len(self.questions):
            data = self.questions[self.current_index]
            self.label_info.config(text=f"問題 {self.current_index + 1} / {len(self.questions)}")
            self.label_question.config(text=data["question"])
            
            self.choice_frame.pack_forget()
            self.input_frame.pack_forget()

            if data["type"] == "choice":
                self.choice_frame.pack()
                for i, opt in enumerate(data["options"]):
                    self.btn_list[i].config(text=opt)
            else:
                self.input_frame.pack()
                self.entry_answer.delete(0, tk.END)
                self.entry_answer.focus_set()
        else:
            self.show_result()

    def check_answer(self, idx, q_type):
        """答えを判定し、解説を表示する"""
        data = self.questions[self.current_index]
        is_correct = False
        correct_text = ""

        # --- 判定ロジック ---
        if q_type == "choice":
            # 4択の場合
            if idx == data["answer"]:
                is_correct = True
            correct_text = data["options"][data["answer"]]
        else:
            # 記述式の場合
            user_input = self.entry_answer.get().strip()
            # 答えが複数ある場合（リスト）と、一つの場合（文字列）の両方に対応
            answers = data["answer"] if isinstance(data["answer"], list) else [data["answer"]]
            if any(user_input.lower() == str(a).lower() for a in answers):
                is_correct = True
            correct_text = answers[0]

        # --- 解説文の取得 ---
        # JSONに "commentary" がない場合は「（解説はありません）」と表示
        commentary = data.get("commentary", "解説は現在準備中です。")

        # --- 音の再生 ---
        self.play_sound(is_correct)

        # --- メッセージの組み立て ---
        title = "✨ 正解 ✨" if is_correct else "残念..."
        
        # 画面に表示するテキスト
        message = f"【正解： {correct_text} 】\n\n"
        message += f"《 解説 》\n{commentary}"

        # ポップアップを表示
        if is_correct:
            self.score += 1
            messagebox.showinfo(title, message)
        else:
            messagebox.showwarning(title, message)
        
        # --- 次の問題へ進む ---
        self.current_index += 1
        self.display_question()
        
    def play_sound(self, is_correct):
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            file = "correct.mp3" if is_correct else "wrong.mp3"
            path = os.path.join(base_dir, "assets", file)
            if os.path.exists(path):
                pygame.mixer.music.load(path)
                pygame.mixer.music.play()
        except:
            pass

    def show_result(self):
        messagebox.showinfo("終了", f"お疲れ様でした！\nスコア: {self.score} / {len(self.questions)}")
        self.setup_category_screen() # カテゴリー選択に戻る

if __name__ == "__main__":
    root = tk.Tk()
    app = QuizApp(root)
    root.mainloop()