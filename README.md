# Ark Re:Code GVG Sniffer

我不知道这是什么，网络和底层并非我擅长的领域，本项目仅出于**个人好奇和折腾**。

## 离线模式

现在直接从官网拉取解包数据，不再写死到本地，仅在数据更新时重新下载。并且可以直接打开浏览器，登陆账号并保存Token了（完全离线，账密不需要经过第三方服务器）。

运行工具集```python3 toolkit.py```（或者下载最新的Release打开toolkit.exe），在账号菜单输入+添加账号，输入-删除账号。

当前支持功能：

1. 刷日常：领取每日登陆奖励，扫塔，佣兵团登陆捐赠，买友情商店等
2. 刷NPC派遣：不进场清NPC，派遣和尝试领取饭点体力
3. 刷活动讨伐：
   - 刷讨伐，元素，活动的最新关卡
   - 一键通关活动前12关
   - 自动战斗**通关活动精英**（需要有一队预设配置合理）
   - 自动战斗**通关深渊**（需要两队预设配置合理）
4. 刷神秘商店：买黄绿票，芯片，并根据我的垃圾小模板买破烂装备
5. 刷星源商店：同上
6. 刷佣兵团周任务：2800
7. 刷亲密度：选第一队刷亲密度
8. 查询团战总结：查询团战的出刀总结（又名压力表）
9. 小众变态工具集
   - 查询前排团战数据：收集全服前20的佣兵团出刀数据存到db中
   - 查询前排团战作业：根据上面收集的db筛选解法
   - 查询前排团战错题本：筛一下输的多的阵容
   - 领取全部成就：或许包含被ch删掉的成就，不确定
   - 领取全部邮件：领取未领取邮件奖励
   - 一键**通关主线爬塔元素讨伐**：能通的直接通，不能的就第一队打
   - JJC定时进场：定时到周一5AM进场
   - 投票：支持光狙谢谢喵（暂时）
   - 团战数据转表格：没什么p用

## 打包

```pyinstaller -F toolkit.py --collect-all frida --collect-all UnityPy --clean --noconfirm --icon=data/icon.ico```

## 一些碎碎念

1. 突然意识到星陨计划有PC端，因此不需要使用模拟器。模拟器的配置方法我放到最下了。

2. 需要注意的是，改了代理之后，必须打开mitmproxy才能联网，因此平常不开mitmproxy的时候，需要在设置里把代理关掉。

3. 最近发现PC端和iOS都能双开星陨计划了，很爽。PC端我用的是[Sandboxie-Plus](https://sandboxie-plus.com/downloads/)，iOS是把官网下的IPA文件通过[EditIPA](https://jagritthukral.github.io/EditIPA/)这个网站修改Bundle Identifier再通过全能签安装。

4. 现在会先下载解包数据生成master.db和master.json，然后通过解包数据来更新活动和角色等信息，不再手动更新了（懒）。

5. 一开始都是纯手撸代码，到后面直接用Codex进行一个Vibe Coding，包括账号登陆部分，GPT太叼了。

## 相关参考

- [Capture-pcr-API](https://github.com/watermellye/Capture-pcr-API)

- [Ark Re:Code Wiki](https://arkrecodewiki.miraheze.org/wiki)

## ~~安装游戏~~

~~安装[星陨计划PC端](https://www.arkrecode.com/)。~~

## ~~配置模拟器~~

1. ~~（PC）安装星陨计划安卓端和[MuMu模拟器](https://mumu.163.com/download/)（我用的是[国际版](https://www.mumuplayer.com/download/)）。~~

2. ~~（模拟器）在设置中打开Root权限和系统盘可读写功能。~~

3. ~~（PC）下载[OpenSSL](https://slproweb.com/products/Win32OpenSSL.html)(我是直接用的Linux版)。~~

4. ~~（PC）获取证书的subject_hash：```openssl x509 -subject_hash_old -in mitmproxy-ca-cert.cer```。这里证书是在```%USERPROFILE%\.mitmproxy\```目录下的，用mitmproxy-ca-cert.cer或者mitmproxy-ca-cert.pem都行。~~

5. ~~（PC）重命名证书：把证书重命名为<OpenSSL输出的第一行的hash>.0（一般是：c8750f0d.0）~~

6. ~~（模拟器）安装[Root Explorer](https://rootexplorer.co/download-apk/)或者类似的可读写系统盘的文件管理器，把根目录mount为读写r/w。~~

7. ~~（模拟器）通过共享文件夹把重命名后的证书传到模拟器，再复制到/etc/security/cacerts/目录下。~~

## ~~安装mitmproxy~~

~~安装[mitmproxy](https://www.mitmproxy.org/)，运行一次。~~

~~```mitmdump```~~

~~首次运行会在```%USERPROFILE%\.mitmproxy\```目录下生成证书，点击```mitmproxy-ca.p12```安装证书。~~

## ~~配置Python~~

~~安装必要的环境，自行选择是否使用Conda之类的包管理器：~~

~~```pip install mitmproxy```~~
~~```pip install crypto```~~
~~```pip install pycryptodome```~~

<details>
  <summary><del>不确定是否必要</del></summary>
  <del>打开site-packages中crypto的安装路径，将crypto改为Crypto（C大写）。</del>
</details>

## ~~在线模式~~

1. ~~克隆仓库到本地```git clone https://github.com/jajajag/arkrecode_gvg_sniffer```~~

2. ~~在命令行（PowerShell 或 Command Prompt）运行```ipconfig```查询你的 IPv4 地址~~

3. ~~打开 设置 → 网络和 Internet → 使用代理服务器 → 设置~~

4. ~~打开 **使用代理服务器**，代理 IP 地址填上面查到的 IPv4 地址，端口填一个数字（例如```1825```）~~

5. ~~运行```mitmdump```并打开游戏```mitmdump -p 1825 -s main.py --quiet```~~

~~当前支持功能：~~

- ~~打开佣兵团 → 查询团战总结~~
- ~~打开 RTA → 查询个房间信息~~
- ~~打开 JJC / 复仇 / 好友 → 查询角色信息~~
