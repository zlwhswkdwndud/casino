import discord
from discord import ui, app_commands
from discord.ext import commands
import sqlite3, random, asyncio, datetime

import os

# ================= [ ⚙️ 설정 ] =================
# 깃허브에 직접 올리지 않고, Render의 Environment Variables에서 가져옵니다.
TOKEN = os.environ.get("DISCORD_TOKEN") 

ADMIN_CHANNEL_ID = 1457737805215170611 
LOG_CHANNEL_ID = 1458433086206382110 
RENT_CHANNEL_ID = 1458081118925619271
ROLE_ID = 1458751429211590656
START_MONEY = 100000
BANK_IMG = "https://cdn.discordapp.com/attachments/1457738870736293993/1457739399038107772/content.png"
CASINO_IMG = "https://media.discordapp.net/attachments/1457738870736293993/1457739447398568182/content.png"

# 대출 한도 및 이율 설정 (방장님 요청대로 하향 조정)
GRADE_DATA = {
    "브론즈": {"rate": 0.08, "limit": 1000000, "up_cost": 10000000, "next": "실버"},
    "실버": {"rate": 0.06, "limit": 10000000, "up_cost": 50000000, "next": "골드"},
    "골드": {"rate": 0.05, "limit": 50000000, "up_cost": 200000000, "next": "플래티넘"},
    "플래티넘": {"rate": 0.04, "limit": 200000000, "up_cost": 1000000000, "next": "다이아"},
    "다이아": {"rate": 0.02, "limit": 1000000000, "up_cost": 0, "next": None}
}



# ---------------- [ 💾 DB 및 로그 함수 ] ----------------
def init_db():
    conn = sqlite3.connect('economy.db'); c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, money INTEGER, loan INTEGER, grade TEXT DEFAULT '브론즈')''')
    conn.commit(); conn.close()

def db_ex(q, p=()):
    conn = sqlite3.connect('economy.db'); c = conn.cursor()
    c.execute(q, p); conn.commit(); conn.close()

def get_u(uid):
    conn = sqlite3.connect('economy.db')
    c = conn.cursor()
    # 컬럼 순서를 id, money, loan, grade로 명확히 지정
    c.execute("SELECT id, money, loan, grade FROM users WHERE id=?", (uid,))
    r = c.fetchone()
    conn.close()
    
    if not r: 
        db_ex("INSERT INTO users (id, money, loan, grade) VALUES (?, 100000, 0, '브론즈')", (uid,))
        return [uid, 100000, 0, '브론즈']
    
    # 만약 DB에 저장된 grade가 None이거나 비어있으면 '브론즈'로 강제 설정
    res = list(r)
    if res[3] is None or res[3] == "":
        res[3] = '브론즈'
    return res

async def send_log(bot, title, user, content, color=0x2b2d31):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        embed = discord.Embed(title=f"📝 {title}", description=content, color=color, timestamp=datetime.datetime.now())
        embed.set_author(name=f"{user.name}", icon_url=user.display_avatar.url)
        await channel.send(embed=embed)

# ------은행 클래스

class BankView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # 유저 정보를 가져오되, 없으면 그 즉시 가입시키는 내부 함수
    def get_or_create_user(self, user_id):
        u = get_u(user_id)
        if not u:
            # DB에 없으면 초기자금 1000원과 함께 자동 생성
            db_ex("INSERT INTO users (id, money, loan, grade) VALUES (?, ?, ?, ?)", (user_id, 100000, 0, "브론즈"))
            u = get_u(user_id)
        return u
    
    # 1. 내 정보 버튼
    @ui.button(label="👤 내 정보", style=discord.ButtonStyle.gray, custom_id="bank_info")
    async def info(self, i: discord.Interaction, b: ui.Button):
        u = get_u(i.user.id)
        current_grade = str(u[3])
        if current_grade not in GRADE_DATA: current_grade = "브론즈"

        max_limit = GRADE_DATA[current_grade]["limit"]
        current_loan = u[2]
        possible_limit = max_limit - current_loan
        rate_percent = int(GRADE_DATA[current_grade]["rate"] * 100)

        embed = discord.Embed(title=f"👤 {i.user.name}님의 자산 보고서", color=0x3498db)
        embed.add_field(name="💰 보유 자산", value=f"{u[1]:,}원", inline=True)
        embed.add_field(name="💸 현재 대출액", value=f"{current_loan:,}원", inline=True)
        embed.add_field(name="🏅 현재 등급", value=f"{current_grade} (이자 {rate_percent}%)", inline=True)
        
        limit_info = (
            f"• 등급 최대 한도: **{max_limit:,}원**\n"
            f"• 추가 대출 가능: **{max(0, possible_limit):,}원**"
        )
        embed.add_field(name="📊 대출 한도 안내", value=limit_info, inline=False)
        embed.set_footer(text="아잉 중앙 은행 - 정직한 금융의 동반자")
        await i.response.send_message(embed=embed, ephemeral=True)

# 2. 대출 신청 (승인/거절 사유/DM/로그 기능 통합)
    @ui.button(label="💰 대출 신청", style=discord.ButtonStyle.green, custom_id="bank_loan")
    async def loan(self, i: discord.Interaction, b: ui.Button):
        class LModal(ui.Modal, title="신규 대출 신청"):
            amt = ui.TextInput(label="신청 금액 (숫자만)")
            async def on_submit(self, it: discord.Interaction):
                try: val = int(self.amt.value.replace(",", ""))
                except: return await it.response.send_message("숫자만 입력해 주세요.", ephemeral=True)
                
                u = get_u(it.user.id)
                grade = str(u[3]) if str(u[3]) in GRADE_DATA else "브론즈"
                limit = GRADE_DATA[grade]["limit"]
                if val + u[2] > limit:
                    return await it.response.send_message(f"🚨 한도 초과! {grade} 최대 한도는 {limit:,}원입니다.", ephemeral=True)
                
                total = int(val * (1 + GRADE_DATA[grade]["rate"]))
                admin_ch = it.client.get_channel(ADMIN_CHANNEL_ID)
                
                if admin_ch:
                    applicant = it.user
                    view = ui.View(timeout=None)

                    # [관리자 승인 버튼 클릭 시]
                    async def approve_cb(itn: discord.Interaction):
                        db_ex("UPDATE users SET money=money+?, loan=loan+? WHERE id=?", (val, total, applicant.id))
                        await itn.response.edit_message(content=f"✅ {itn.user.mention} 관리자가 <@{applicant.id}>님 대출 **승인**", view=None)
                        
                        # 로그 채널 전송
                        log_ch = itn.client.get_channel(RENT_CHANNEL_ID)
                        if log_ch:
                            l_emb = discord.Embed(title="💰 대출 승인 로그", color=0x2ecc71, timestamp=itn.created_at)
                            l_emb.add_field(name="대출자", value=applicant.mention, inline=True)
                            l_emb.add_field(name="관리자", value=itn.user.mention, inline=True)
                            l_emb.add_field(name="금액", value=f"입금: {val:,}원 / 상환: {total:,}원", inline=False)
                            await log_ch.send(embed=l_emb)
                        
                        # 유저 DM 알림
                        try: await applicant.send(f"🏦 **대출 승인**: {val:,}원이 입금되었습니다. (상환액: {total:,}원)")
                        except: pass

                    # [관리자 거절 버튼 클릭 시]
                    async def deny_cb(itn: discord.Interaction):
                        class DenyModal(ui.Modal, title="거절 사유 입력"):
                            reason = ui.TextInput(label="사유", placeholder="거절 사유를 입력하세요", style=discord.TextStyle.paragraph)
                            async def on_submit(self, itnn: discord.Interaction):
                                await itn.edit_original_response(content=f"❌ {itnn.user.mention} 관리자가 <@{applicant.id}>님 대출 **거절**\n**사유:** {self.reason.value}", view=None)
                                # 유저 DM 알림
                                try: await applicant.send(f"🏦 **대출 거절**: {self.reason.value}")
                                except: pass
                                await itnn.response.send_message("거절 완료", ephemeral=True)
                        await itn.response.send_modal(DenyModal())

                    btn_ok = ui.Button(label="✅ 승인", style=discord.ButtonStyle.green)
                    btn_no = ui.Button(label="❌ 거절", style=discord.ButtonStyle.red)
                    btn_ok.callback, btn_no.callback = approve_cb, deny_cb
                    view.add_item(btn_ok); view.add_item(btn_no)

                    await admin_ch.send(f"🚨 **대출 요청**\n신청자: {applicant.mention}\n액수: {val:,}원", view=view)
                    await it.response.send_message("✅ 대출 신청 완료!", ephemeral=True)
        await i.response.send_modal(LModal())

    # 3. 대출 상환 버튼
    @ui.button(label="💸 대출 상환", style=discord.ButtonStyle.red, custom_id="bank_repay")
    async def repay(self, i: discord.Interaction, b: ui.Button):
        class RModal(ui.Modal, title="대출 상환"):
            amt = ui.TextInput(label="상환할 금액 (숫자만)")
            async def on_submit(self, it: discord.Interaction):
                try: val = int(self.amt.value.replace(",", ""))
                except: return await it.response.send_message("숫자만 입력해 주세요.", ephemeral=True)
                u = get_u(it.user.id)
                if u[2] <= 0: return await it.response.send_message("상환할 대출금이 없습니다.", ephemeral=True)
                r_amt = min(val, u[2])
                if u[1] < r_amt: return await it.response.send_message("잔액이 부족합니다.", ephemeral=True)
                db_ex("UPDATE users SET money=money-?, loan=loan-? WHERE id=?", (r_amt, r_amt, it.user.id))
                await it.response.send_message(f"✅ {r_amt:,}원 상환 완료!", ephemeral=True)
        await i.response.send_modal(RModal())

    # 4. 등급 승급 버튼 (여기가 사라졌던 부분입니다!)
    # 4. 등급 승급 버튼 (실수 방지 2차 확인 버전)
    @ui.button(label="⏫ 등급 승급", style=discord.ButtonStyle.primary, custom_id="bank_upgrade")
    async def upgrade(self, i: discord.Interaction, b: ui.Button):
        u = get_u(i.user.id)
        current_grade = str(u[3])
        if current_grade not in GRADE_DATA: current_grade = "브론즈"
        
        next_grade = GRADE_DATA.get(current_grade, {}).get("next")
        
        if not next_grade:
            return await i.response.send_message("이미 최고 등급(다이아)입니다!", ephemeral=True)
        
        cost = GRADE_DATA[current_grade]["up_cost"]

        # --- 2차 확인용 내부 뷰 클래스 ---
        class UpgradeConfirmView(ui.View):
            def __init__(self, cost, next_grade):
                super().__init__(timeout=30) # 30초 내에 안 누르면 무효화
                self.cost = cost
                self.next_grade = next_grade

            @ui.button(label="💰 승급 진행하기", style=discord.ButtonStyle.danger)
            async def confirm(self, itn: discord.Interaction, btn: ui.Button):
                # 버튼 클릭 시점에 돈이 있는지 다시 한 번 체크
                u_check = get_u(itn.user.id)
                if u_check[1] < self.cost:
                    return await itn.response.edit_message(content=f"🚫 그새 돈이 부족해졌습니다! (필요: {self.cost:,}원)", view=None)
                
                # 실제 DB 처리
                db_ex("UPDATE users SET money = money - ?, grade = ? WHERE id = ?", (self.cost, self.next_grade, itn.user.id))
                
                # 로그 전송
                await send_log(itn.client, "등급 승급 성공", itn.user, f"이전: {u_check[3]} ➔ 현재: {self.next_grade}\n차감액: {self.cost:,}원", 0x9b59b6)
                
                await itn.response.edit_message(content=f"🎊 **승급 완료!** 이제 **{self.next_grade}** 등급입니다!", view=None)

            @ui.button(label="취소", style=discord.ButtonStyle.secondary)
            async def cancel(self, itn: discord.Interaction, btn: ui.Button):
                await itn.response.edit_message(content="❌ 승급 신청을 취소했습니다.", view=None)

        # 유저에게 먼저 물어봄
        confirm_embed = discord.Embed(
            title="⚠️ 등급 승급 최종 확인",
            description=f"정말로 승급을 진행하시겠습니까?\n\n"
                        f"• 현재 등급: **{current_grade}**\n"
                        f"• 다음 등급: **{next_grade}**\n"
                        f"• 소모 비용: **{cost:,}원**\n\n"
                        f"아래 [승급 진행하기] 버튼을 누르면 즉시 돈이 차감됩니다.",
            color=0xf1c40f
        )
        await i.response.send_message(embed=confirm_embed, view=UpgradeConfirmView(cost, next_grade), ephemeral=True)

# 송금하기 버튼 (기존 BankView 안에 추가)
    @ui.button(label="🤝 송금하기", style=discord.ButtonStyle.success, custom_id="bank_remit")
    async def remit(self, i: discord.Interaction, b: ui.Button):
        class UserSelectView(ui.View):
            def __init__(self, sender_id):
                super().__init__(timeout=60)
                self.sender_id = sender_id

            @ui.select(cls=ui.UserSelect, placeholder="돈을 받을 멤버를 선택하세요")
            async def select_user(self, it: discord.Interaction, select: ui.UserSelect):
                target_user = select.values[0]
                
                class AmtModal(ui.Modal, title=f"{target_user.display_name}님에게 송금"):
                    amt = ui.TextInput(label="보낼 금액 (10% 수수료 차감)")
                    async def on_submit(self, itn: discord.Interaction):
                        try: val = int(self.amt.value.replace(",", ""))
                        except: return await itn.response.send_message("숫자만 입력해 주세요.", ephemeral=True)

                        if target_user.id == itn.user.id: 
                            return await itn.response.send_message("본인에게는 보낼 수 없습니다.", ephemeral=True)
                        
                        s, r = get_u(itn.user.id), get_u(target_user.id)
                        if not r: return await itn.response.send_message("가입하지 않은 유저입니다.", ephemeral=True)
                        if val <= 0 or s[1] < val: return await itn.response.send_message("잔액 부족 또는 잘못된 금액입니다.", ephemeral=True)

                        tax = int(val * 0.1)
                        real_amt = val - tax

                        # 1. DB 정산
                        db_ex("UPDATE users SET money=money-? WHERE id=?", (val, itn.user.id))
                        db_ex("UPDATE users SET money=money+? WHERE id=?", (real_amt, target_user.id))

                        # 2. 지정된 채널로 로그 전송
                        log_ch = itn.client.get_channel(LOG_CHANNEL_ID)
                        if log_ch:
                            l_emb = discord.Embed(title="🏦 송금 로그", color=0xffffff, timestamp=itn.created_at)
                            l_emb.add_field(name="보낸 사람", value=f"{itn.user.mention} ({itn.user.id})", inline=False)
                            l_emb.add_field(name="받은 사람", value=f"{target_user.mention} ({target_user.id})", inline=False)
                            l_emb.add_field(name="금액 정보", value=f"원금: {val:,}원\n수수료: {tax:,}원\n최종 입금: {real_amt:,}원", inline=False)
                            await log_ch.send(embed=l_emb)

                        # 3. 채널 응답 및 DM 발송
                        await itn.response.send_message(f"✅ {target_user.mention}님께 {val:,}원 송금을 완료했습니다!", ephemeral=True)

                        # 보낸 사람 DM
                        try:
                            s_emb = discord.Embed(title="🏦 아잉은행 송금 영수증", color=0x3498db)
                            s_emb.description = f"**{target_user.display_name}**님께 {val:,}원을 보냈습니다. (수수료 {tax:,}원 차감)"
                            await itn.user.send(embed=s_emb)
                        except: pass

                        # 받은 사람 DM
                        try:
                            r_emb = discord.Embed(title="🏦 아잉은행 입금 알림", color=0x2ecc71)
                            r_emb.description = f"**{itn.user.display_name}**님으로부터 {real_amt:,}원이 입금되었습니다."
                            await target_user.send(embed=r_emb)
                        except: pass
                
                await it.response.send_modal(AmtModal())

        await i.response.send_message("어떤 멤버에게 돈을 보낼까요?", view=UserSelectView(i.user.id), ephemeral=True)
 
# ---------------- [ 🎰 카지노 세부 기능 구현 ] ----------------


class CasinoModal(ui.Modal):
    def __init__(self, title, mode):
        super().__init__(title=title); self.mode = mode
        self.bet = ui.TextInput(label="배팅 금액 (숫자만)"); self.add_item(self.bet)
        if mode == "horse": self.choice = ui.TextInput(label="말 번호 (1번~5번)"); self.add_item(self.choice)

    async def on_submit(self, itn):
        try: b = int(self.bet.value.replace(",",""))
        except: return await itn.response.send_message("금액은 숫자로 입력하세요.", ephemeral=True)
        u = get_u(itn.user.id)
        if b <= 0 or b > u[1]: return await itn.response.send_message("보유 자산이 부족하거나 잘못된 금액입니다.", ephemeral=True)
        db_ex("UPDATE users SET money=money-? WHERE id=?", (b, itn.user.id))

# 1. 🎲 홀짝 (승률 43% 조작 + 배당 1.8배)
        if self.mode == "hl":
            v = ui.View()
            
            async def hl_proc(i: discord.Interaction, select: str):
                # [수정] 버튼 누르자마자 응답 처리 (에러 방지 핵심)
                await i.response.edit_message(content="🎲 주사위 컵을 흔드는 중...", view=None)
                
                # 애니메이션 추가 (원하시면 넣고, 싫으시면 이 for문만 지우세요)
                for _ in range(3):
                    await i.edit_original_response(content=f"🎲 **두구두구...** {random.choice(['⚀','⚁','⚂','⚃','⚄','⚅'])}")
                    await asyncio.sleep(0.4)

                luck = random.randint(1, 100)
                ans = select if luck <= 43 else ("짝" if select == "홀" else "홀")
                win = int(b * 1.8) if select == ans else 0
                
                db_ex("UPDATE users SET money=money+? WHERE id=?", (win, i.user.id))
                
                res_txt = f"🎊 **적중!** {win:,}원 획득" if win > 0 else "💀 **낙첨** (봇의 승리)"
                
                # [수정] original_response().edit 대신 edit_original_response 사용
                await i.edit_original_response(content=f"🎲 결과: **{ans}**\n{res_txt}")
                await send_log(i.client, "홀짝", i.user, f"배팅: {b:,}원 | 선택: {select} | 결과: {ans}\n정산: {win:,}원")

            # [수정] lambda 대신 직접 함수 연결 시 발생하는 문법 오류 해결
            for l in ["홀", "짝"]:
                btn = ui.Button(label=l, style=discord.ButtonStyle.primary)
                # lambda 대신 이 방식을 쓰는 게 가장 문법적으로 깔끔합니다.
                def make_callback(label):
                    async def callback(interaction):
                        await hl_proc(interaction, label)
                    return callback
                
                btn.callback = make_callback(l)
                v.add_item(btn)
                
            await itn.response.send_message(f"🎲 홀짝 중 하나를 선택하세요! (배팅: {b:,}원)", view=v, ephemeral=True)

        # 2. ✌️ 애니메이션 가위바위보
        elif self.mode == "rsp":
            v = ui.View()
            async def rsp_proc(i: discord.Interaction, p_c: str):
                # 1. 봇의 최종 패 결정
                b_c = random.choice(["가위", "바위", "보"])
                icons = {"가위": "✌️", "바위": "✊", "보": "✋"}
                
                # 2. 우선 "상태 업데이트"를 위해 defer() 또는 edit_message() 호출
                await i.response.edit_message(content="**가위... 바위...**", view=None)
                
                # 3. 봇의 패가 바뀌는 애니메이션 연출 (3회 반복)
                for _ in range(3):
                    for emoji in icons.values():
                        await i.edit_original_response(content=f"봇이 고민 중... {emoji}")
                        await asyncio.sleep(0.15) # 회전 속도 조절

                # 4. 결과 판정
                if p_c == b_c: 
                    res, win = "무승부 🤝", b
                elif (p_c=="가위" and b_c=="보") or (p_c=="바위" and b_c=="가위") or (p_c=="보" and b_c=="바위"): 
                    res, win = "승리! 🎉", b*2
                else: 
                    res, win = "패배 💀", 0
                
                # 5. DB 정산
                db_ex("UPDATE users SET money=money+? WHERE id=?", (win, i.user.id))
                
                # 6. 최종 결과 출력
                final_msg = (
                    f"### {res}\n"
                    f"👤 나: **{p_c}** {icons[p_c]}\n"
                    f"🤖 봇: **{b_c}** {icons[b_c]}\n\n"
                    f"💰 정산액: **{win:,}원**"
                )
                await i.edit_original_response(content=final_msg)
                
                # 로그 기록
                await send_log(itn.client, "가위바위보", itn.user, f"배팅: {b:,}원 | {p_c} vs {b_c}\n결과: {res}")

            # 버튼 생성
            for choice in ["가위", "바위", "보"]:
                btn = ui.Button(label=choice, style=discord.ButtonStyle.success)
                btn.callback = lambda interaction, c=choice: rsp_proc(interaction, c)
                v.add_item(btn)
            
            await itn.response.send_message(f"가위바위보! 선택하세요! (배팅액: {b:,}원)", view=v, ephemeral=True)

       # 3. 🎰 슬롯머신 (애니메이션 및 임베드 결과)
        elif self.mode == "slot":
            # 1. 🏁 초기 응답 (ephemeral=True로 본인만 보이게)
            await itn.response.send_message("🎰 슬롯머신 레버를 당깁니다! (777: 50배 | 💩3개: -2배)", ephemeral=True)
            
            icons = ["🍎", "🍊", "🍇", "💎", "7️⃣", "💩"]
            
            # 2. 🎬 릴 스탑(Reel Stop) 애니메이션 연출
            # 아이콘이 하나씩 순차적으로 멈추는 느낌을 줍니다.
            final_res = [random.choice(icons) for _ in range(3)] # 결과 미리 결정
            display = ["🌀", "🌀", "🌀"] # 돌아가는 모양

            for i in range(3): # 첫 번째 칸부터 하나씩 멈춤
                for _ in range(3): # 돌아가는 효과
                    temp = [random.choice(icons) if j >= i else final_res[j] for j in range(3)]
                    await itn.edit_original_response(content=f"🎰 [ {temp[0]} | {temp[1]} | {temp[2]} ]")
                    await asyncio.sleep(0.3)
                display[i] = final_res[i] # 해당 칸 고정

            # 3. 📊 정밀한 배당 판정
            res = final_res
            u_cnt = len(set(res))
            win = 0
            detail_msg = ""

            if u_cnt == 1: # 3개 일치
                if res[0] == "7️⃣": 
                    win = int(b * 50); detail_msg = "🔥 대박! 잭팟 777 터졌습니다! 🔥"
                elif res[0] == "💩": 
                    win = int(b * -2); detail_msg = "🤮 으악! 똥통에 빠졌습니다! (배팅금 2배 압수)"
                else: 
                    win = int(b * 10); detail_msg = f"✨ {res[0]} 트리플! 10배 당첨! ✨"
            elif u_cnt == 2: # 2개 일치 (보너스)
                win = int(b * 1.2); detail_msg = "🤏 아깝네요! 2개 일치로 1.2배 보상!"
            else: # 꽝
                win = 0; detail_msg = "💀 다음 기회에... (아무것도 맞지 않음)"

            # 4. 💳 DB 정산 및 로그
            db_ex("UPDATE users SET money = money + ? WHERE id = ?", (win, itn.user.id))
            
            # 5. 🖼️ 결과 임베드 디자인
            if win > 0:
                clr = 0x2ecc71 if win >= b * 10 else 0xf1c40f
                tit = "🎊 슬롯머신 결과: WIN!"
            elif win < 0:
                clr = 0x000000
                tit = "💩 슬롯머신 결과: BAD LUCK!"
            else:
                clr = 0xe74c3c
                tit = "💀 슬롯머신 결과: LOSE"

            emb = discord.Embed(title=tit, description=f"## [ {res[0]} | {res[1]} | {res[2]} ]\n{detail_msg}", color=clr)
            emb.add_field(name="💰 배팅 금액", value=f"{b:,}원", inline=True)
            emb.add_field(name="💵 정산 결과", value=f"{win:,}원", inline=True)
            emb.set_footer(text=f"현재 잔액은 /지갑 명령어로 확인하세요!")

            await itn.edit_original_response(content=None, embed=emb)
            await send_log(itn.client, "슬롯", itn.user, f"배팅:{b} | 결과:{''.join(res)} | 정산:{win}")

       # 4. 🐎 경마 (실시간 중계 애니메이션)
        elif self.mode == "horse":
            try: 
                pick = int(self.choice.value)
                if not (1 <= pick <= 5): raise ValueError
            except: 
                return await itn.response.send_message("말 번호는 1~5번 중에서 골라주세요!", ephemeral=True)

            # 초기 설정
            horses = ["🏇", "🏇", "🏇", "🏇", "🏇"]
            positions = [0] * 5  # 각 말의 위치 (0~15)
            goal = 15 # 결승선 거리
            track_length = 15
            
            # 1. 경기 시작 선언
            embed = discord.Embed(title="🏇 영암 경마장 - 경기 시작!", color=0x3498db)
            embed.description = f"선택한 말: **{pick}번마**\n배팅 금액: **{b:,}원**\n\n" + "🏁" + "-" * track_length + "┓\n"
            for i in range(5):
                embed.description += f"{i+1}번 | " + " " * track_length + "┃\n"
            embed.description += "🏁" + "-" * track_length + "┛"
            
            await itn.response.send_message(embed=embed, ephemeral=True)

            # 2. 실시간 경기 진행 애니메이션
            finished = False
            winner = None
            
            for _ in range(20): # 최대 20턴 내에 종료
                if finished: break
                await asyncio.sleep(1.2) # 중계 간격
                
                # 말들 전진 (랜덤하게 0~3칸)
                for i in range(5):
                    positions[i] += random.randint(0, 3)
                    if positions[i] >= goal:
                        positions[i] = goal
                        if not finished:
                            winner = i + 1
                            finished = True

                # 트랙 화면 업데이트
                race_track = "🏁" + "-" * track_length + "┓\n"
                for i in range(5):
                    # 말의 위치 표시
                    p = positions[i]
                    lane = [" "] * track_length
                    if p < track_length:
                        lane[track_length - 1 - p] = horses[i]
                    else:
                        lane[0] = "🚩" # 결승선 통과 시 깃발
                    
                    race_track += f"{i+1}번 |" + "".join(lane) + "┃\n"
                race_track += "🏁" + "-" * track_length + "┛"

                update_embed = discord.Embed(title="🏇 영암 경마장 - 경기 진행 중!", color=0x3498db)
                update_embed.description = f"선택한 말: **{pick}번마**\n\n" + race_track
                await itn.edit_original_response(embed=update_embed)

            # 3. 결과 정산
            win_amount = b * 5 if pick == winner else 0
            db_ex("UPDATE users SET money=money+? WHERE id=?", (win_amount, itn.user.id))

            # 4. 최종 결과 발표
            result_color = 0x2ecc71 if win_amount > 0 else 0xe74c3c
            result_embed = discord.Embed(title="🏁 경기 종료!", color=result_color)
            
            if win_amount > 0:
                result_embed.description = f"### 🎉 축하합니다! {winner}번마 우승!\n당첨금으로 **{win_amount:,}원**을 획득하셨습니다!"
            else:
                result_embed.description = f"### 💀 아쉽습니다. {winner}번마 우승!\n{pick}번마는 결승선에 늦게 도착했습니다."

            result_embed.set_footer(text=f"최종 순위: {winner}번마 1등")
            await itn.edit_original_response(embed=result_embed)

            # 로그 기록
            await send_log(itn.client, "경마", itn.user, f"배팅: {b:,}원 | 선택: {pick}번 | 우승: {winner}번 | 정산: {win_amount:,}원")



# ---------------- [ 🤖 봇 기능 통합 및 실행 ] ----------------
class YeongamBot(commands.Bot):
    def __init__(self): super().__init__(command_prefix="!", intents=discord.Intents.all())
    async def setup_hook(self): init_db(); await self.tree.sync()

bot = YeongamBot()

@bot.tree.command(name="돈지급", description="[관리자] 특정 유저에게 자금을 지급합니다.")
async def give(itn, target: discord.User, amount: int):
    if not itn.user.guild_permissions.administrator: return await itn.response.send_message("관리자만 사용 가능합니다.", ephemeral=True)
    db_ex("UPDATE users SET money = money + ? WHERE id = ?", (amount, target.id))
    await send_log(itn.client, "자산 강제 지급", itn.user, f"대상: {target.mention}\n금액: {amount:,}원", 0x3498db)
    await itn.response.send_message(f"✅ {target.display_name}님에게 {amount:,}원을 지급했습니다.", ephemeral=True)

@bot.tree.command(name="은행전체세팅")
async def bset(itn):
    embed = discord.Embed(title="🏦 아잉 중앙 은행", description="안전한 자산 관리와 신속한 대출 서비스를 제공합니다.\n\n"
                    "**이용 가능 서비스**\n"
                    "└ `내 정보` : 자산 및 대출 현황 확인\n"
                    "└ `대출 신청/상환` : 등급별 한도 내 대출, 대출 후 원금 갚기\n"
                    "└ `승급` : 회원 등급 업그레이드 (업그레이드 시 대출 한도 UP!)", color=0x2b2d31)
    embed.set_image(url=BANK_IMG)
    await itn.channel.send(embed=embed, view=BankView())
    await itn.response.send_message("은행 서비스 세팅이 완료되었습니다.", ephemeral=True)

@bot.tree.command(name="카지노전체세팅")
async def cset(itn):
    embed = discord.Embed(title="🎰 아잉 카지노 (Ah Ing Casino)", description="인생을 바꿀 단 한 번의 기회! 다양한 게임을 즐겨보세요.\n\n"
                    "**🎲 게임 리스트**\n"
                    "└ `슬롯머신` : 777을 맞추면 배팅금의 50배!\n"
                    "└ `가위바위보` : 봇과 대결하여 승리 시 2배!\n"
                    "└ `경마` : 5마리 말 중 우승마 예측 시 4배! \n"
                    "└ `홀짝` : 50%의 승률 보장! 예측 시 1.8배! ", color=0xffd700)
    embed.set_image(url=CASINO_IMG)
    v = ui.View()
    games = [("🎰 슬롯머신", "slot"), ("✌️ 가위바위보", "rsp"), ("🏇 경마 게임", "horse"), ("🎲 홀짝 게임", "hl")]
    for n, cid in games:
        v.add_item(ui.Button(label=n, custom_id=cid, style=discord.ButtonStyle.secondary))
    await itn.channel.send(embed=embed, view=v)
    await itn.response.send_message("카지노 게임 세팅이 완료되었습니다.", ephemeral=True)

@bot.listen("on_interaction")
async def game_listener(itn):
    if itn.type == discord.InteractionType.component:
        cid = itn.data.get("custom_id")
        if cid in ["slot", "rsp", "horse", "hl"]:
            await itn.response.send_modal(CasinoModal(cid.upper(), cid))

# --- 순위 대시보드 기능 (코드 맨 아래에 붙여넣으세요) ---

def create_rank_embed():
    import sqlite3
    conn = sqlite3.connect('economy.db')
    c = conn.cursor()
    # 자산 순으로 상위 10명 조회
    c.execute("SELECT id, money, grade FROM users ORDER BY money DESC LIMIT 10")
    top_list = c.fetchall()
    conn.close()

    embed = discord.Embed(
        title="🏆 아잉 서버 자산 순위", 
        description="현재 서버의 최고 부자들입니다.",
        color=0xffd700,
        timestamp=datetime.datetime.now()
    )

    if not top_list:
        embed.add_field(name="데이터 없음", value="아직 등록된 유저가 없습니다.")
    else:
        rank_text = ""
        for i, (uid, money, grade) in enumerate(top_list, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"**{i}.**"
            rank_text += f"{medal} <@{uid}> | `{grade}` | **{money:,}원**\n"
        embed.add_field(name="랭킹 리스트", value=rank_text, inline=False)
    
    embed.set_footer(text="아잉 중앙 관리 시스템")
    return embed

class RankView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @ui.button(label="🔄 순위 새로고침", style=discord.ButtonStyle.primary, custom_id="refresh_rank")
    async def refresh(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(embed=create_rank_embed())

@bot.tree.command(name="순위세팅", description="[관리자] 자산 순위 대시보드를 생성합니다.")
async def rank_setup(itn: discord.Interaction):
    if not itn.user.guild_permissions.administrator:
        return await itn.response.send_message("관리자 권한이 필요합니다.", ephemeral=True)
    await itn.channel.send(embed=create_rank_embed(), view=RankView())
    await itn.response.send_message("✅ 순위 대시보드 세팅 완료!", ephemeral=True)

# ---------------- [ ⚙️ 은행 세팅 명령어 ] ----------------

@bot.tree.command(name="은행세팅", description="[관리자] 은행 서비스 시스템을 이 채널에 생성합니다.")
async def bank_setup(itn: discord.Interaction):
    if not itn.user.guild_permissions.administrator:
        return await itn.response.send_message("관리자 권한이 필요합니다.", ephemeral=True)
    
    embed = discord.Embed(
        title="🏦 아잉 은행 (Yeongam Bank)", 
        description="안전하고 빠른 금융 서비스를 제공합니다.\n\n"
                    "**[ 버튼 기능 안내 ]**\n"
                    "👤 **내 정보** : 현재 자산, 대출액, 등급 확인\n"
                    "💰 **대출 신청** : 등급 한도 내 대출 신청 (관리자 승인제)\n"
                    "💸 **대출 상환** : 대출 원금 및 이자 상환\n"
                    "⏫ **등급 승급** : 등급을 올려 대출 한도를 증액", 
        color=0x3498db
    )
    embed.set_image(url=BANK_IMG)
    await itn.channel.send(embed=embed, view=BankView())
    await itn.response.send_message("✅ 은행 시스템 세팅 완료!", ephemeral=True)

# --- [/가입메시지전송 명령어] ---
@bot.tree.command(name="가입메시지전송", description="고급 가입 안내 임베드를 생성합니다.")
async def send_join_msg(i: discord.Interaction):
    if not i.user.guild_permissions.administrator:
        return await i.response.send_message("관리자만 사용 가능합니다.", ephemeral=True)

    embed = discord.Embed(
        title="🏦 영암은행 서비스 이용자 등록",
        description="영암은행의 모든 금융 서비스를 이용하시려면 아래 버튼을 눌러 등록을 완료해 주세요.",
        color=0x2ecc71 # 초록색
    )
    
    embed.add_field(
        name="🎁 가입 혜택", 
        value=f"• 가입 축하금 **{START_MONEY:,}원** 즉시 지급\n• 은행 전용 채널 입장 권한 부여\n• 대출 및 송금 서비스 이용 가능", 
        inline=False
    )
    
    embed.add_field(
        name="📜 이용 약관", 
        value="• 타인 비방 및 불법 자금 세탁 금지\n• 과도한 대출은 파산의 원인이 될 수 있습니다.", 
        inline=False
    )
    
    embed.set_footer(text="버튼을 누르는 즉시 약관에 동의하는 것으로 간주됩니다.")
    embed.set_thumbnail(url=i.guild.icon.url if i.guild.icon else None)

    await i.channel.send(embed=embed, view=RegisterView())
    await i.response.send_message("가입 메시지를 성공적으로 띄웠습니다!", ephemeral=True)

@bot.event
async def on_ready():
    # 봇이 켜질 때 버튼(View)들을 미리 등록해두는 과정입니다.
    # 이렇게 해야 봇을 껐다 켜도 예전에 보낸 버튼들이 작동합니다.
   # bot.add_view(RegisterView()) 
    bot.add_view(BankView())
    
    # 봇이 정상적으로 켜졌는지 확인용 출력
    print(f"✅ {bot.user.name} 봇이 준비되었습니다!")
    try:
        synced = await bot.tree.sync()
        print(f"✅ 슬래시 명령어 {len(synced)}개 동기화 완료!")
    except Exception as e:
        print(f"❌ 명령어 동기화 중 오류 발생: {e}")

bot.run(TOKEN)
