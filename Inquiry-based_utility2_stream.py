from openai import OpenAI
import json
import random
import base64
import numpy as np
import os
from utility3 import tidy_det, conn_det, sr_det_ans_final, circuit_design_det
from page_render import render_page
import uuid
import cv2

SERVER_IP_ADDR = "192.168.4.195"

SERVER_DIR = os.path.dirname(__file__)

class APIGetException(Exception):
    def __init__(self, *args):
        super().__init__(*args)

class ChatProcess:
    
    PHASE2NAME = {
        "question": "情景导入",
        "evidence": "设计思考",
        "analysis": "实验验证",
        "discussion": "总结思考",
        "evaluation": "整体评价"
    }
    
    def __init__(self, config):
        self.config = config                    # 配置文件
        self.steps = self.getstep(config)       # 阶段和步骤
        self.currentStep = 0                    # 当前步骤，从0开始计数
        self.stepCount = len(self.steps)        # 步骤总数
        self.history = {
            "start": {
                "desc": "接下去将生成问题让学生回答\n",               
                "title": "阶段开始",
                "type": "START"
            },
        }                                       # 历史记录
        self.answer_times   = 0                   # 当前问题学生回答次数
        self.question       = None                    # 当前正在回答的问题
        self.issr           = False
        self.switch_closed  = False
        self.connecting     = False
        self.zero_ajust     = False
        
        # self.client = OpenAI(api_key='sk-4vj3NYKrgqfUfHSDVD4xkiuOuBpOlo6jGY0kWiq6ioUXswoC', 
        #         base_url="https://api.hunyuan.cloud.tencent.com/v1")
        # self.client = OpenAI(api_key='sk-OWwbeu95SJyl88LXVaN4WWq3SuPHrnrLGAhSdU0tZJMiYiDv',
        #         base_url="https://api.planetzero.live/v1/")
        self.client = OpenAI(api_key  = "sk-abcdefghijklmnopqrstuvwxyz123456", 
                             base_url = "http://192.168.4.195:8889/v1")
        # self.client = OpenAI(api_key='ollama',
        #                 base_url="http://223.2.29.223:11434/v1/")

    def init_state(self):
        self.currentStep = 0
        self.history = {
             "start": {
                "desc": "接下去将生成问题让学生回答\n",               
                "title": "阶段开始",
                "type": "START"              
            }
        }
        self.answer_times = 0
        self.connecting = False
        self.question = None
        self.zero_ajust = False
        self.issr           = False
        self.switch_closed  = False
        

    def getTans(self, prompt, history, useHis=False, stream=True):
        if not useHis :
            messages = [{"role":"user","content":prompt}]
        else:
            messages = [{"role":"system","content":history}]
            message_prompt = {"role":"user","content":prompt}
            messages.append(message_prompt)
        try:
            if not stream:
                response = self.client.chat.completions.create(
                    model="Qwen2.5",
                    messages=messages,
                    temperature=0.7
                )
                return response.choices[0].message.content

            response = self.client.chat.completions.create(
                model="Qwen2.5",
                messages=messages,
                temperature=0.7,
                stream=True,
            )
            return response                
        except Exception as e:
            print(f"API调用失败：{e}")
            raise APIGetException()

    def getstep(self,data):
        all_steps = []
        for stage_name, stage_data in data.items():
            for key in stage_data:
                if not key.startswith("desc"):  # 忽略 desc开头
                    all_steps.append((stage_name, key))
        return all_steps 
    
    '''
    :进行下一步，会根据当前状态自动切换下一步
    '''
    def next(self, result=None):
        if self.currentStep >= self.stepCount:
            self.init_state()
            return self.getEndInfo()

        phase, step = self.steps[self.currentStep]
        input_t = self.config[phase][step]["format"]["input"]
        
        if f"{phase}-{step}" not in self.history:
            self.history[f"{phase}-{step}"] = dict()
            self.history[f"{phase}-{step}"]["desc"] = f"现在是{ChatProcess.PHASE2NAME[phase]}阶段{step}\n"
            if "point" in self.config[phase][step]:
                self.history[f"{phase}-{step}"]["point"] = dict()
                for point in self.config[phase][step]["point"]:
                    self.history[f"{phase}-{step}"]["point"][point] = {
                        "max": float(self.config[phase][step]["score"][point]),
                        "get": 0.0
                    }

        if input_t == "":
            self.history[f"{phase}-{step}"]["type"] = "QUES"
            return self.step_question(result)
        elif input_t == "table":
            self.history[f"{phase}-{step}"]["type"] = "TABLE"
            return self.step_table(result)
        elif input_t == "circuit":
            self.history[f"{phase}-{step}"]["type"] = "CIRCUIT"
            return self.step_circuit(result)
        elif input_t == "connection":
            self.history[f"{phase}-{step}"]["type"] = "CONN"
            self.connecting = True
            return self.step_connection(result)
        elif input_t == "record":
            self.history[f"{phase}-{step}"]["type"] = "RECORD"
            return self.step_record(result)
        elif input_t == "tidyUp":
            self.history[f"{phase}-{step}"]["type"] = "TIDYUP"
            return self.step_tidyup(result)
        elif input_t == "evaluation":
            self.history[f"{phase}-{step}"]["type"] = "EVAL"
            return self.step_evaluation(result)

    def processUIRImg(self, data):
        img_byte = base64.b64decode(data['data'])       
        img_name = f"{uuid.uuid4()}.jpg"
        with open(os.path.join(SERVER_DIR, f"sum_pages/imgs/{img_name}"), "wb") as fout:
            fout.write(img_byte)
        
        self.history[data["type"]] = {
            "type": data["type"],
            "img-url": f"http://{SERVER_IP_ADDR}:8000/sum_page/imgs/{img_name}",
            "ispass": data["pass"]
        }

    def streamOtherOK(self):
        pahse, step = self.steps[self.currentStep]
        prompt = self.config[pahse][step]["promptTrue"]
        if self.connecting:
            prompt += "，当前为电路连接判断阶段，生成的评价不要提连接的具体情况。"
            
            if self.issr:
                prompt += "并且，当前的滑动变阻器处于最大阻值状态，满足实验要求，在生成的评价中要简要提及。"
            else:
                prompt += "并且，当前的滑动变阻器不处于最大阻值状态，不满足实验要求，在生成的评价中要简要提及。"
            
            if self.switch_closed:
                prompt += "并且，当前的开关处于闭合状态，不满足实验要求，在生成的评价中要简要提及。"
            else:
                prompt += "并且，当前的开关处于断开状态，满足实验要求，在生成的评价中要简要提及。"
                
            if self.zero_ajust:
                prompt += "并且，学生进行了调零，满足实验要求，在生成的评价中要简要提及。"
            else:
                prompt += "并且，学生没有进行调零，不满足实验要求，在生成的评价中要简要提及。"
            
            self.connecting = False
        res = self.getTans(prompt, "")
        self.currentStep += 1
        try:
            for chunk in res:
                cont = chunk.choices[0].delta.content
                yield cont
        except:
            raise APIGetException()

    def streamOtherErr(self):
        pahse, step = self.steps[self.currentStep]
        prompt = self.config[pahse][step]["promptFalse"]
        if self.connecting:
            prompt += "，当前为电路连接判断阶段，生成的评价不要提连接的具体情况。"
            if self.issr:
                prompt += "并且，当前的滑动变阻器处于最大阻值状态，满足实验要求，在生成的评价要在另外一句中简要提及。"
            else:
                prompt += "并且，当前的滑动变阻器不处于最大阻值状态，不满足实验要求，在生成的评价要在另外一句中简要提及。"
            
            if self.switch_closed:
                prompt += "并且，当前的开关处于闭合状态，不满足实验要求，在生成的评价中要简要提及。"
            else:
                prompt += "并且，当前的开关处于断开状态，满足实验要求，在生成的评价中要简要提及。"
                
            if self.zero_ajust:
                prompt += "并且，学生进行了调零，满足实验要求，在生成的评价中要简要提及。"
            else:
                prompt += "并且，学生没有进行调零，不满足实验要求，在生成的评价中要简要提及。"
            
            self.connecting = False
        res = self.getTans(prompt, "")
        self.currentStep += 1
        try:
            for chunk in res:
                cont = chunk.choices[0].delta.content
                yield cont
        except:
            raise APIGetException()

    def streamOtherTip(self):
        pahse, step = self.steps[self.currentStep]
        prompt = self.config[pahse][step]["prompt"]
        res = self.getTans(prompt, "")
        try:
            for chunk in res:
                cont = chunk.choices[0].delta.content
                yield cont
        except:
            raise APIGetException()

    def streamGetQuesOK(self):
        prompt = f'当前问题为：\n{self.question["question"]}\n其答案为: {self.question["key"]}\n该学生回答的答案正确，请以温和的语气给出评价，并对正确答案作出解析。注意语言要简短，且为不带任何格式的纯文本'
        res = self.getTans(prompt, "")
        self.currentStep += 1
        self.answer_times = 0
        try:
            for chunk in res:
                cont = chunk.choices[0].delta.content
                self.question["question"] += cont
                yield cont
        except:
            raise APIGetException()

    def streamGetQuesRetry(self):
        prompt = f'当前问题为：\n{self.question["question"]}\n其答案为: {self.question["key"]}\n该学生回答的答案错误，错误选项为{self.question["w_ans"]}，请以温和的语气给出评价，评价中只能讨论学生提交的错误选项的解析，不能涉及正确选项的任何信息，对学生回答的答案作出解析并提醒他再试一次。注意语言要简短，且为不带任何格式的纯文本'
        res = self.getTans(prompt, "")
        self.answer_times += 1
        try:
            for chunk in res:
                cont = chunk.choices[0].delta.content
                self.question["question"] += cont
                yield cont
        except:
            raise APIGetException()
        
    def streamGetQuesEr(self):
        prompt = f'当前问题为：\n{self.question["question"]}\n其答案为: {self.question["key"]}\n该学生已经两次回答错误，请以温和的语气给出评价，告诉他正确答案并给出解析，一定要告诉他正确答案是{self.question["key"]}。注意语言要简短，且为不带任何格式的纯文本'
        res = self.getTans(prompt, "")
        self.currentStep += 1
        self.answer_times = 0
        try:
            for chunk in res:
                cont = chunk.choices[0].delta.content
                self.question["question"] += cont
                yield cont
        except:
            raise APIGetException()

    def streamGetQuestion(self):
        phase, step = self.steps[self.currentStep]
        desc1 = self.config[phase]['desc1']
        desc2 = self.config[phase][step]["desc"]            
        example = self.config[phase][step]["prompt"]["example"]
        ques = example["question"]
        options = example["options"]
        ans = example["answer"]
        gen_key = chr(random.randint(0, 3) + ord('A'))
        
        prompt = f"{desc1}，当前步骤的目的为{desc2}\n例如：\n{ques}\n"
        for key in options:
            prompt += f"{key} {options[key]}\n"
        prompt += f"正确答案为：{ans}\n"
        prompt += f"请你为我生成类似的提问和答案选项，要求正确答案不变，提问方式进行简单改变。只要问题和选项沣意只要输出这两项，不要任何提示文本，不要出现任何和功率相关的内容，遵循我给的样例，不要生成任何评价。在你生成的问题中，新生成请 确保{gen_key}选项为正确答案"
        
        res = self.getTans(prompt, "")
        self.question = {
            "key": gen_key,
            "question": ""
        }
        
        try:
            for chunk in res:
                cont = chunk.choices[0].delta.content
                self.question["question"] += cont
                yield cont
        except:
            raise APIGetException()
      
 
    def setCurrentStep(self, idx):
        if idx < 0 and idx >= self.stepCount:
            print("Idx Invaild!")
        self.init_state()
        self.currentStep  = idx
          
    def startStepByIdx(self, idx):
        self.setCurrentStep(idx)
        return self.next()

    def sumup_plus(self):
        phase, step = self.steps[self.currentStep]
        history_prompt = '''
        学生进行了一个探究电流电压电阻关系的初中物理实验，我会给你一个评分细则和学生的实验过程记录。实验过程记录中有一些操作记录和答题情况，你要对比两者，分析学生在各个环节是否能够得分，在进行分析时，你应该避免使用step这样的代号，而是描述具体的信息。同时对于一些没有出现在评分细则里的问题，你也要对学生的整体答题情况进行详细的评价，分析学生会将问题答错的原因可能是什么，不少于100字。最后，你还应该对照每一条科学核心素养对学生整体表现进行评价。并给出对学生的建议。以下是评分细则以及科学核心素养

        评分细则
        1. 猜想并设计实验（15%）
        1.1 提出合理的猜想假设（5%）- 对应设计思考中的stepA-D
        1.2 设计实验电路图（5%）- 对应实验验证中的stepC
        1.3 设计实验表格（5%）- 对应实验验证中的stepF和stepH

        2. 电路连接（15%）
        2.4 开关断开时连接电路（5%）- 现在是阶段实验验证步骤stepD,判断连接电路时开关是否断开
        2.5 正确连接电流表、电压表、电阻和滑动变阻器（5%）- 现在是阶段实验验证步骤stepD,判断电连接是否正确
        2.6 闭合电路前滑动变阻器滑片位于电阻最大位置（5%）- 现在是阶段实验验证步骤stepD,判断滑动变阻器是否在最大位置  

        3. 探究关系（30%）
        3-1 探究电流与电压的关系（15%）
            3.7 移动滑动变阻器使电压表示数为 1V、2V、3V，记录电流（10%）- 对应实验验证中的stepG
            记录三组数据并绘制 U-I 图像（5%）- 对应实验验中的stepG
        3-2 探究电流与电阻的关系（15%）
            更换电阻使电压保持 3V，记录电流（10%）- 对应实验验证中的stepI
            记录三组数据并绘制 R-I 图像（5%）- 对应实验验证中的stepI

        4. 仪器检查与整理（10%）
        4.8 检查并调零电流表、电压表（5%）现在是阶段实验验证步骤stepD，学生是否有检查仪器，对电流表、电压表进行调零
        4.9 拆除电路，整理实验仪器（5%）- 对应实验验证中的stepI，判断是否整理仪器

        5. 总结归纳（20%）
        5.10 总结电流与电压、电阻的关系（20%）- 对应总结思考的 StepC

        6. 交流讨论（10%）
        6.11 讨论实验问题、改进措施或提出其他合理问题（10%）

        科学核心素养：
        1、科学观念
        指学生对自然界和科学本质的基本理解。
        2、科学思维
        指学生在科学学习中形成的理性思考方式。
        3、科学探究
        指学生通过动手实践和科学方法主动获取知识的能力。
        4、态度与责任
        指学生在学习和应用科学时所表现出的价值观和责任感。
                        
        以下是学生的实验过程记录：
        接下去学生开始实验
        '''
        for p, s in self.steps[:-1]:
            if f"{p}-{s}" in self.history:
                history_prompt += self.history[f"{p}-{s}"]["desc"]
                
        answer = self.getTans(history_prompt, "", False, False)
        page_name = f"{uuid.uuid4()}.html"
        answer = render_page(answer, self.history, os.path.join(SERVER_DIR, "sum_pages", page_name))
        self.currentStep += 1
        
        return {
            "html": answer,
            "url": f"/sum_page/{page_name}"
        }


    def sumup(self):
        phase, step = self.steps[self.currentStep]
        history_prompt = ""
        for p, s in self.steps[:-1]:
            if f"{p}-{s}" in self.history:
                history_prompt += self.history[f"{p}-{s}"]["desc"]
        
        mission = self.config[phase][step]["prompt"]["mission"]
        mission["学生回答情况"] = history_prompt
        prompt = "学生刚刚完成了一个探究电流、电阻和电压关系的初中实验流程。你要根据学生回答问题的情况，电路图表格设计的准确度，进行一个整体的评价\n"
        prompt += "这是学生回答问题的情况，以及电路图表格设计的情况，请你为我生成整体的评价,按我的json格式输出\n"
        prompt += f"{mission}"
        answer = self.getTans(prompt, "", False, False)
        start_idx = answer.find('{')  
        end_idx = answer.rfind('}') 
        json_string = answer[start_idx:end_idx+1]
        res_obj = json.loads(json_string)
        self.currentStep += 1
        return res_obj

    def step_evaluation(self, result):
        phase, step = self.steps[self.currentStep]
        if result == None:
            return {
                "type": "SUM_TIP",
                "phase": phase,
                "reply": "你已经完成了所有实验步骤，点击生成实验报告获取最终评价。"
            }
        else:
            return {
                "type": "SUM_GET",
                "phase": phase,
                "reply": self.sumup_plus()
            }  

    '''
    :处理普通问答
    '''
    def step_question(self, result):
        phase, step = self.steps[self.currentStep]
        if self.answer_times == 0:   
            if result != None:                              # 学生第一次回答问题
                self.history[f"{phase}-{step}"]["desc"] += self.question["question"]
                self.history[f"{phase}-{step}"]["desc"] += f'学生第一次回答问题给出答案:{result["answer"]}\n'
                if self.judge_answer(result) == True:
                    self.history[f"{phase}-{step}"]["ispass"] = True
                    comment = self.getOKComment()
                    return comment
                else:
                    return self.getRetryComment(result)
            else:                                           # 学生没有回答这个问题且回答次数为0，说明还没给出问题，大模型生成问题，发送给学生
                ques = self.getQuestion()
                return ques
        else:
            if result != None:                              # 学生第二次回答问题
                self.history[f"{phase}-{step}"]["desc"] += f'学生第二次回答问题给出答案:{result["answer"]}\n'
                if self.judge_answer(result) == True:
                    self.history[f"{phase}-{step}"]["ispass"] = True
                    comment = self.getOKComment()
                    return comment
                else:
                    self.history[f"{phase}-{step}"]["ispass"] = False
                    comment = self.getFailedComment()
                    return comment
            else:
                self.history[f"{phase}-{step}"]["ispass"] = False
                comment = self.getFailedComment()
                return comment


    def judge_answer(self, res):
        phase, step = self.steps[self.currentStep]
        try:
            return res["answer"] == self.question["key"]
        except:
            return False

    def getOKComment(self):
        phase, step = self.steps[self.currentStep]
        
        if "point" in self.history[f"{phase}-{step}"]:
            for pk in self.history[f"{phase}-{step}"]["point"]:
                pt = self.history[f"{phase}-{step}"]["point"][pk]
                self.history[f"{phase}-{step}"]["point"][pk]["get"] = pt["max"]

        comment = {
            "type": "QUES_OK", 
        }
        
        return comment

    def getRetryComment(self, res):
        phase, step = self.steps[self.currentStep]
        self.question["w_ans"] = res["answer"]
        comment = {
            "type": "QUES_RETRY",
        }
        return comment

    def getQuestion(self):
        phase, step = self.steps[self.currentStep]
        self.history[f"{phase}-{step}"]["desc"] += "问题为："
        return {
            "type": "QUES_GET",
            "phase": phase,
            "step": step,
        }

    def getFailedComment(self):
        comment = {
            "type": "QUES_FAILED",
        }
        return comment
    
    '''
    : 处理表格回复
    '''
    def step_table(self, result):
        phase, step = self.steps[self.currentStep]
        if result == None:              # 没有结果，说明还没给出提示，生成提示对话
            comment = self.getTableTip()
            return comment
        else:                           # 结果不为空，学生给出了table，给出评价
            self.history[f"{phase}-{step}"]["title"] = f"设计{result['table_type']}表格\n"
            if self.judgeTable(result):
                self.history[f"{phase}-{step}"]["desc"] = "学生成功设计表格\n"
                self.history[f"{phase}-{step}"]["ispass"] = True
                return self.getTableOK()   
            else:
                self.history[f"{phase}-{step}"]["desc"] = "学生设计表格出现错误\n"
                self.history[f"{phase}-{step}"]["ispass"] = False
                return self.getTableErr()               

    def getTableTip(self):
        phase, step = self.steps[self.currentStep]
        return {
            "type": "TABLE_GET",
            "table_type": self.config[phase][step]["table_type"],
            "phase": phase,
            "step": step,
        }

    def getTableOK(self):
        
        phase, step = self.steps[self.currentStep]
        for pk in self.history[f"{phase}-{step}"]["point"]:
            pt = self.history[f"{phase}-{step}"]["point"][pk]
            self.history[f"{phase}-{step}"]["point"][pk]["get"] = pt["max"]
        
        comment = {
            "type": "TABLE_OK",
        }
        return comment

    def getTableErr(self):
        phase, step = self.steps[self.currentStep]
        comment = {
            "type": "TABLE_ER",
            "table": self.config[phase][step]["right_table"]
        }
        return comment

    '''
    : 判定表格设计正确与否，当前在前端判断，故后端只需要判断前端返回的是否为OK
    '''
    def judgeTable(self, res):
        try :
            data = res["data"]
            
            phase, step = self.steps[self.currentStep]
            self.history[f"{phase}-{step}"]["table"] = res["data"]
            self.history[f"{phase}-{step}"]["table-type"] = res["table_type"]
            
            if len(data) < 4:
                return False
            if len(data[0]) != 3:
                return False
            
            if data[0][0]["type"] != "label" or data[0][0]["value"] != "序号":
                return False
            for idx,  c in enumerate(data[1:]):
                if c[0]["type"] != "label" or str(idx + 1) != c[0]["value"]:
                    return False

            for r in data[1:]:
                for c in r[1:]:
                    if c["type"] != "input":
                        return False

            if data[0][1]["type"] != "label" or data[0][2]["type"] != "label":
                return False 

            if res["table_type"] == "UI":
                if "电压" in data[0][1]["value"] and "电流" in data[0][2]["value"]:
                    return True
                if "电压" in data[0][2]["value"] and "电流" in data[0][1]["value"]:
                    return True
            elif res["table_type"] == "IR":
                if "电阻" in data[0][1]["value"] and "电流" in data[0][2]["value"]:
                    return True
                if "电阻" in data[0][2]["value"] and "电流" in data[0][1]["value"]:
                    return True
            return False
        except:
            return False


    '''
    : 处理电路图设计回复
    '''
    def step_circuit(self, result):   
        phase, step = self.steps[self.currentStep]
        self.history[f"{phase}-{step}"]["title"] = "电路图设计"  
        if result == None:              # 没有结果，说明还没给出提示，生成提示对话
            comment = self.getCircuitTip()
            return comment
        else:                           # 结果不为空，学生给出了电路图设计结果，大模型给出评价
            if self.judgeCircuit(result):
                self.history[f"{phase}-{step}"]["desc"] = "学生成功设计电路\n"  
                self.history[f"{phase}-{step}"]["ispass"] = True 
                return self.getCircuitOK()   
            else:
                self.history[f"{phase}-{step}"]["desc"] = "学生设计的电路有错误\n"  
                self.history[f"{phase}-{step}"]["ispass"] = False
                return self.getCircuitErr() 
    
    def getCircuitTip(self):
        phase, step = self.steps[self.currentStep]
        return {
            "type": "CIRCUIT_GET",
            "phase": phase,
            "step": step,
        }

    def judgeCircuit(self, res):
        try :
            img_byte = base64.b64decode(res['b64'])       
            img_name = f"{uuid.uuid4()}.jpg"
            with open(os.path.join(SERVER_DIR, f"sum_pages/imgs/{img_name}"), "wb") as fout:
                fout.write(img_byte)
            phase, step = self.steps[self.currentStep]
            self.history[f"{phase}-{step}"]["img-url"] = f"http://{SERVER_IP_ADDR}:8000/sum_page/imgs/{img_name}"
            
            res, ans = circuit_design_det(json.loads(res["data"]))            
            return res
        except:
            return False

    def getCircuitOK(self):
        
        phase, step = self.steps[self.currentStep]
        for pk in self.history[f"{phase}-{step}"]["point"]:
            pt = self.history[f"{phase}-{step}"]["point"][pk]
            self.history[f"{phase}-{step}"]["point"][pk]["get"] = pt["max"]
        
        comment = {
            "type": "CIRCUIT_OK",
        }
        return comment

    def getCircuitErr(self):
        comment = {
            "type": "CIRCUIT_ER",
        }
        return comment

    '''
    : 处理实物连接回复
    '''
    def step_connection(self, result):
        phase, step = self.steps[self.currentStep]
        self.history["zero-va"] = {
            "type": "ZERO",
            "point": {
                "5.1": {
                    "get": 5.0 if self.zero_ajust else 0.0,
                    "max": 5.0
                }
            }
        }
        self.history[f"{phase}-{step}"]["title"] = "实物图连接"

        if result == None:              # 没有结果，说明还没给出提示，大模型生成提示对话
            comment = self.getConnectionTip()
            return comment
        else:                           # 结果不为空，学生给出了实物连接结果，大模型给出评价
            if self.judgeConnection(result):
                self.history[f"{phase}-{step}"]["desc"] = "学生成功连接电路\n"
                self.history[f"{phase}-{step}"]["ispass"] = True
                return self.getOKConnection()   
            else:
                self.history[f"{phase}-{step}"]["desc"] = "学生连接电路出错\n"
                self.history[f"{phase}-{step}"]["ispass"] = False
                return self.getErrConnection() 
    
    def getConnectionTip(self):
        phase, step = self.steps[self.currentStep]
        return {
            "type": "CONN_GET",
            "phase": phase,
            "step": step,
        }

    def save_img(self, img):
        phase, step = self.steps[self.currentStep]
        img_name = f"{uuid.uuid4()}.jpg"
        img_path = os.path.join(SERVER_DIR, "sum_pages", "imgs", img_name)
        cv2.imwrite(img_path, img)
        self.history[f"{phase}-{step}"]["img-url"] = os.path.join(f"http://{SERVER_IP_ADDR}:8000/sum_page/imgs/{img_name}")
        
        return f"http://{SERVER_IP_ADDR}:8000/sum_page/imgs/{img_name}"

    ## HSY
    def judgeConnection(self, res):
        
        try :
            img = res["data"]
            w, h, c = res["w"], res["h"], res["c"]
            img = np.frombuffer(base64.b64decode(img), dtype=np.uint8).reshape(h, w, c)
            conn_img_url = self.save_img(img)
            self.history["zero-va"]["img-url"] = conn_img_url
            self.switch_closed = True
            self.issr = sr_det_ans_final(img)
            res, self.switch_closed = conn_det(img)
            return res
        except:
            return False

    def getOKConnection(self):
        try:
            phase, step = self.steps[self.currentStep]
            connpt = self.history[f"{phase}-{step}"]["point"]
            connpt["2.2"]["get"] = connpt["2.2"]["max"]
            if self.issr:
                connpt["2.3"]["get"] = connpt["2.3"]["max"]
            if not self.switch_closed: 
                connpt["2.1"]["get"] = connpt["2.1"]["max"]
            self.history[f"{phase}-{step}"]["point"] = connpt
        except:
            pass
        
        comment = {
            "type": "CONN_OK",
        }
        return comment

    def getErrConnection(self):
        try:
            phase, step = self.steps[self.currentStep]
            connpt = self.history[f"{phase}-{step}"]["point"]
            if self.issr:
                connpt["2.3"]["get"] = connpt["2.3"]["max"]
            if not self.switch_closed: 
                connpt["2.1"]["get"] = connpt["2.1"]["max"]
            self.history[f"{phase}-{step}"]["point"] = connpt
        except:
            pass
        comment = {
            "type": "CONN_ER",
        }
        return comment

    '''
    : 处理实验结束时的回复
    '''
    def getEndInfo(self):
        return {
            "type": "END",
            "reply": "实验结束"
        }
    
    '''
    处理表格记录过程 
    '''
    def step_record(self, result):
        phase, step = self.steps[self.currentStep]
        if result == None:
            return self.getStartRecordAns()
        else:
            self.history[f"{phase}-{step}"]["title"] = f"填写{result['table_type']}表格数据"
            if self.judegRecord(result):
                self.history[f"{phase}-{step}"]["desc"] = f"学生{result['table_type']}表格数据填写正确\n"
                self.history[f"{phase}-{step}"]["ispass"] = True
                comment = self.getOKRecordAns(result)
                return comment
            else:
                self.history[f"{phase}-{step}"]["desc"] = f"学生{result['table_type']}表格数据填写错误\n"
                self.history[f"{phase}-{step}"]["ispass"] = False
                comment = self.getFailedRecordAns(result)
                return comment
    
    def getStartRecordAns(self):
        phase, step = self.steps[self.currentStep]
        return {
            "type": "RECORD_GET",
            "table_type": self.config[phase][step]["table_type"],
            "phase": phase,
            "step": step,
        }
    
    def judegRecord(self, res):
        try:
            data = res["data"]
            
            phase, step = self.steps[self.currentStep]
            self.history[f"{phase}-{step}"]["table"] = res["data"]
            self.history[f"{phase}-{step}"]["table-type"] = res["table_type"]
            
            x = []
            y = []
            if "电流" in data[0][1]["value"]:
                for it in data[1:]:
                    x.append(float(it[1]["value"]))
                    y.append(float(it[2]["value"]))
            else:
                for it in data[1:]:
                    x.append(float(it[2]["value"]))
                    y.append(float(it[1]["value"]))
            
            if res["table_type"] == "UI":
                z = []
                for xi, yi in zip(x, y):
                    z.append(yi/xi)
                mz = sum(z)/len(z)
                for zi in z:
                    if abs(zi-mz) > 5:
                        return False
            elif res["table_type"] == "IR":
                z = []
                for xi, yi in zip(x, y):
                    z.append(yi*xi)
                mz = sum(z)/len(z)
                for zi in z:
                    if abs(zi-mz) > 1:
                        return False
            return True
        except:
            return False
    
    def getOKRecordAns(self, res):
        phase, step = self.steps[self.currentStep]
        
        for pk in self.history[f"{phase}-{step}"]["point"]:
            pt = self.history[f"{phase}-{step}"]["point"][pk]
            self.history[f"{phase}-{step}"]["point"][pk]["get"] = pt["max"]
        
        comment = {
            "type": "RECORD_OK",
            "table_type": self.config[phase][step]["table_type"]
        }
        return comment
    
    def getFailedRecordAns(self, res):
        comment = {
            "type": "RECORD_ER",
        }
        return comment
    
    '''
    处理仪器整理
    '''
    def step_tidyup(self, result):
        phase, step = self.steps[self.currentStep]
        self.history[f"{phase}-{step}"]["title"] = "整理桌面"
        if result == None:
            return self.getStartTidyupAns()
        else:
            if self.judegTidyup(result):
                self.history[f"{phase}-{step}"]["desc"] = "学生完成了桌面整理\n"
                self.history[f"{phase}-{step}"]["ispass"] = True
                comment = self.getOKTidyupAns(result)
                return comment
            else:
                self.history[f"{phase}-{step}"]["desc"] = "学生未完成桌面整理\n"
                self.history[f"{phase}-{step}"]["ispass"] = False
                comment = self.getFailedTidyupAns(result)
                return comment

    def getStartTidyupAns(self):
        phase, step = self.steps[self.currentStep]
        return {
            "type": "TIDYUP_GET",
            "phase": phase,
            "step": step,
        }
    
    def judegTidyup(self, res):
        try:
            img = res["data"]
            w, h, c = res["w"], res["h"], res["c"]
            img = np.frombuffer(base64.b64decode(img), dtype=np.uint8).reshape(h, w, c)
            self.save_img(img)
            is_tidy = tidy_det(img)
            return is_tidy
        except Exception:
            return False
    
    def getOKTidyupAns(self, res):
        
        phase, step = self.steps[self.currentStep]
        
        for pk in self.history[f"{phase}-{step}"]["point"]:
            pt = self.history[f"{phase}-{step}"]["point"][pk]
            self.history[f"{phase}-{step}"]["point"][pk]["get"] = pt["max"]
        
        comment = {
            "type": "TIDYUP_OK",
        }
        return comment
    
    def getFailedTidyupAns(self, res):
        comment = {
            "type": "TIDYUP_ER",
        }
        return comment

'''
测试代码
'''
if __name__ == "__main__":
    SERVER_DIR = os.path.dirname(__file__)
    file_path = os.path.join(SERVER_DIR, '1_config.json')
    with open(file_path, 'r', encoding='utf-8') as file:
        config = json.load(file)
    process = ChatProcess(config)
    process.setCurrentStep(3)
    process.streamGetQuestion()
    