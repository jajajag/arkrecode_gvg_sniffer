# Ark Re:Code GVG Sniffer

我不知道这是什么，也不推荐任何人使用。网络和底层并非我擅长的领域，本项目仅出于**个人好奇和折腾**。

## 安装模拟器

安装[MuMu模拟器](https://mumu.163.com/download/)（我用的是[国际版](https://www.mumuplayer.com/download/)）和[星陨计划](https://www.arkrecode.com/)。

## 安装mitmproxy

安装[mitmproxy](https://www.mitmproxy.org/)，运行一次。

```
mitmdump
```

首次运行会在```%USERPROFILE%\.mitmproxy\```目录下生成证书，点击```mitmproxy-ca.p12```安装证书。

## 配置Python

安装必要的环境，自行选择是否使用Conda之类的包管理器：

```
pip install mitmproxy
pip install crypto
pip install pycryptodome
```

<details>
<summary>不确定是否必要</summary>
打开site-packages中crypto的安装路径，将crypto改为Crypto（C大写）。
</details>

## 配置模拟器

1. （模拟器）在设置中打开Root权限和系统盘可读写功能。

2. （PC）下载[OpenSSL](https://slproweb.com/products/Win32OpenSSL.html)(我是直接用的Linux版)。

3. （PC）获取证书的subject_hash：```openssl x509 -subject_hash_old -in mitmproxy-ca-cert.cer```。这里证书是在```%USERPROFILE%\.mitmproxy\```目录下的，用mitmproxy-ca-cert.cer或者mitmproxy-ca-cert.pem都行。

4. （PC）重命名证书：把证书重命名为<OpenSSL输出的第一行的hash>.0（一般是：c8750f0d.0）

5. （模拟器）安装[Root Explorer](https://rootexplorer.co/download-apk/)或者类似的可读写系统盘的文件管理器，把根目录mount为读写r/w。

6. （模拟器）通过共享文件夹把重命名后的证书传到模拟器，再复制到/etc/security/cacerts/目录下。

## 运行

1. （PC）用ipconfig查询你的IPv4地址。

2. （模拟器）打开设置->网络和互联网->互联网->右侧的齿轮设置->右上角的笔图标->高级选项。

3. （模拟器）将代理改为手动，代理主机名填上面查到的IPv4地址，代理端口随便填一个数字（比如1825）。

4. （PC）```git clone https://github.com/jajajag/arkrecode_gvg_sniffer```本目录到本地，然后调用```mitmdump -p 1825 -s main.py --quiet```运行程序，打开游戏即可。

## 一些碎碎念

1. 需要注意的是，在模拟器改了代理之后，必须打开mitmproxy才能联网，因此平常不开mitmproxy的时候，需要在模拟器里把代理关掉。

2. 最近发现PC端和iOS都能双开星陨计划了，很爽。PC端我用的是[Sandboxie-Plus](https://sandboxie-plus.com/downloads/)，iOS是把官网下的IPA文件通过[EditIPA](https://editipa.jagritthukral.tech/)这个网站修改Bundle Identifier再通过全能签安装。

3. 注意data.json里面也包含己方信息，而且装备副属性是全的，千万不要泄露了当内鬼。

## 相关参考

- [Capture-pcr-API](https://github.com/watermellye/Capture-pcr-API)

- [Ark Re:Code Wiki](https://arkrecodewiki.miraheze.org/wiki)
