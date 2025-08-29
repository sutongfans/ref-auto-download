#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
HuggingFace Daily Papers 下载器 - 修复版
解决原始代码无法获取论文的问题
'''

import os
import re
import json
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
import time

class HuggingFaceDownloader:
    def __init__(self, config):
        self.logger = logging.getLogger("huggingface_scraper.downloader")
        self.config = config
        
        # 基础URL配置
        self.base_url = "https://huggingface.co"
        self.papers_url = f"{self.base_url}/papers"
        
        # 目录配置
        self.download_dir = Path(config.get("paths", "download_dir", 
                                          fallback="downloaded_papers"))
        self.state_dir = Path(config.get("paths", "state_dir", 
                                       fallback="state"))
        
        self.download_dir.mkdir(exist_ok=True, parents=True)
        self.state_dir.mkdir(exist_ok=True, parents=True)
        
        # 请求头配置
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }
        
        # 下载配置
        self.max_papers = config.getint("huggingface", "max_papers", fallback=10)
        self.timeout = config.getint("huggingface", "request_timeout", fallback=30)
        self.retry_count = config.getint("huggingface", "retry_count", fallback=3)
        self.delay = config.getfloat("huggingface", "request_delay", fallback=1.0)

    def fetch_paper_list(self):
        '''获取论文列表 - 使用多种方法'''
        papers = []
        
        # 方法1: 尝试解析主页面
        try:
            self.logger.info(f"正在访问: {self.papers_url}")
            response = self._make_request(self.papers_url)
            
            if response and response.status_code == 200:
                # 首先尝试从页面中提取JSON数据
                papers = self._extract_papers_from_json(response.text)
                
                # 如果JSON提取失败，尝试HTML解析
                if not papers:
                    papers = self._parse_html_papers(response.text)
                
                if papers:
                    self.logger.info(f"成功获取 {len(papers)} 篇论文")
                    return papers
                    
        except Exception as e:
            self.logger.error(f"获取论文列表失败: {e}")
        
        # 方法2: 尝试API端点
        papers = self._try_api_endpoints()
        
        return papers

    def _make_request(self, url, **kwargs):
        '''发送HTTP请求，带重试机制'''
        for attempt in range(self.retry_count):
            try:
                response = requests.get(
                    url, 
                    headers=self.headers, 
                    timeout=self.timeout,
                    **kwargs
                )
                if response.status_code == 200:
                    return response
                else:
                    self.logger.warning(f"请求返回状态码: {response.status_code}")
                    
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"请求失败 (尝试 {attempt + 1}/{self.retry_count}): {e}")
                if attempt < self.retry_count - 1:
                    time.sleep(self.delay * (attempt + 1))
                    
        return None

    def _extract_papers_from_json(self, html_content):
        '''从HTML中的JSON数据提取论文信息'''
        papers = []
        
        # 查找包含论文数据的script标签
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 查找Next.js数据
        script_tag = soup.find('script', id='__NEXT_DATA__')
        if script_tag:
            try:
                data = json.loads(script_tag.string)
                papers = self._parse_nextjs_data(data)
                if papers:
                    self.logger.info("从__NEXT_DATA__中提取到论文")
                    return papers
            except json.JSONDecodeError:
                pass
        
        # 查找其他可能的JSON数据
        for script in soup.find_all('script'):
            if script.string and 'papers' in script.string.lower():
                try:
                    # 尝试提取JSON对象
                    json_match = re.search(r'\{.*"papers".*\}', script.string, re.DOTALL)
                    if json_match:
                        data = json.loads(json_match.group())
                        papers = self._extract_papers_from_data(data)
                        if papers:
                            return papers
                except:
                    continue
        
        return papers

    def _parse_html_papers(self, html_content):
        '''解析HTML获取论文信息'''
        papers = []
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 多种可能的选择器
        selectors = [
            'article',
            'div[class*="paper"]',
            'a[href*="/papers/"]',
            'div[data-test*="paper"]',
            'section article',
            'main article'
        ]
        
        elements = []
        for selector in selectors:
            found = soup.select(selector)
            if found:
                self.logger.info(f"使用选择器 '{selector}' 找到 {len(found)} 个元素")
                elements = found
                break
        
        # 解析每个元素
        for element in elements[:self.max_papers] if self.max_papers > 0 else elements:
            paper = self._extract_paper_from_element(element)
            if paper:
                papers.append(paper)
        
        # 如果还是没找到，尝试查找所有包含arxiv链接的元素
        if not papers:
            arxiv_links = soup.find_all('a', href=re.compile(r'arxiv\.org'))
            for link in arxiv_links[:self.max_papers]:
                paper = self._extract_paper_from_arxiv_link(link)
                if paper:
                    papers.append(paper)
        
        return papers

    def _extract_paper_from_element(self, element):
        '''从HTML元素提取论文信息'''
        paper = {}
        
        # 提取标题
        title_tags = ['h1', 'h2', 'h3', 'h4', 'h5', 'a']
        for tag in title_tags:
            title_elem = element.find(tag)
            if title_elem and title_elem.text.strip():
                paper['title'] = title_elem.text.strip()
                break
        
        # 提取链接
        links = element.find_all('a', href=True)
        for link in links:
            href = link['href']
            
            # 检查是否是论文链接
            if '/papers/' in href:
                paper['url'] = urljoin(self.base_url, href)
                
                # 提取paper ID
                paper_id_match = re.search(r'/papers/(\d+\.\d+)', href)
                if paper_id_match:
                    paper_id = paper_id_match.group(1)
                    paper['pdf_url'] = f"https://arxiv.org/pdf/{paper_id}.pdf"
                    paper['arxiv_id'] = paper_id
                    
            elif 'arxiv.org' in href:
                # 直接的arxiv链接
                arxiv_id_match = re.search(r'(\d+\.\d+)', href)
                if arxiv_id_match:
                    arxiv_id = arxiv_id_match.group(1)
                    paper['pdf_url'] = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                    paper['arxiv_id'] = arxiv_id
                    paper['url'] = href
        
        # 提取作者
        author_elem = element.find(text=re.compile(r'by\s+', re.I))
        if author_elem:
            paper['authors'] = author_elem.strip().replace('by ', '')
        
        # 提取日期
        paper['date'] = datetime.now().strftime('%Y-%m-%d')
        
        # 只返回有PDF链接的论文
        return paper if paper.get('pdf_url') else None

    def _extract_paper_from_arxiv_link(self, link_elem):
        '''从arxiv链接提取论文信息'''
        href = link_elem.get('href', '')
        arxiv_id_match = re.search(r'(\d+\.\d+)', href)
        
        if arxiv_id_match:
            arxiv_id = arxiv_id_match.group(1)
            
            # 获取父元素中的标题
            parent = link_elem.parent
            title = ''
            
            # 向上查找包含标题的元素
            for _ in range(3):  # 最多向上查找3层
                if parent:
                    text = parent.get_text(strip=True)
                    if len(text) > 10 and len(text) < 300:  # 合理的标题长度
                        title = text
                        break
                    parent = parent.parent
            
            if not title:
                title = link_elem.get_text(strip=True) or f"Paper {arxiv_id}"
            
            return {
                'title': title,
                'url': href,
                'pdf_url': f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                'arxiv_id': arxiv_id,
                'date': datetime.now().strftime('%Y-%m-%d')
            }
        
        return None

    def _try_api_endpoints(self):
        '''尝试各种可能的API端点'''
        papers = []
        
        # 可能的API端点
        api_endpoints = [
            f"{self.base_url}/api/papers",
            f"{self.base_url}/api/daily-papers",
            f"{self.base_url}/api/papers/daily",
            f"{self.base_url}/papers/api/list"
        ]
        
        for endpoint in api_endpoints:
            try:
                self.logger.info(f"尝试API端点: {endpoint}")
                response = self._make_request(endpoint)
                
                if response and response.status_code == 200:
                    try:
                        data = response.json()
                        papers = self._parse_api_response(data)
                        if papers:
                            self.logger.info(f"从API获取到 {len(papers)} 篇论文")
                            return papers
                    except json.JSONDecodeError:
                        pass
                        
            except Exception as e:
                self.logger.debug(f"API端点失败: {endpoint}, 错误: {e}")
        
        return papers

    def _parse_api_response(self, data):
        '''解析API响应'''
        papers = []
        
        # 处理不同的API响应格式
        if isinstance(data, list):
            # 直接是论文列表
            for item in data:
                paper = self._normalize_paper_data(item)
                if paper:
                    papers.append(paper)
                    
        elif isinstance(data, dict):
            # 查找包含论文的字段
            for key in ['papers', 'data', 'items', 'results']:
                if key in data and isinstance(data[key], list):
                    for item in data[key]:
                        paper = self._normalize_paper_data(item)
                        if paper:
                            papers.append(paper)
                    break
        
        return papers

    def _normalize_paper_data(self, item):
        '''标准化论文数据'''
        if not isinstance(item, dict):
            return None
        
        paper = {}
        
        # 标题
        for key in ['title', 'name', 'paper_title']:
            if key in item:
                paper['title'] = item[key]
                break
        
        # arxiv ID
        for key in ['arxiv_id', 'paper_id', 'id']:
            if key in item:
                arxiv_id = str(item[key])
                if re.match(r'\d+\.\d+', arxiv_id):
                    paper['arxiv_id'] = arxiv_id
                    paper['pdf_url'] = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                    break
        
        # URL
        for key in ['url', 'link', 'href']:
            if key in item:
                paper['url'] = item[key]
                break
        
        # 如果有URL但没有PDF链接，尝试从URL提取
        if paper.get('url') and not paper.get('pdf_url'):
            arxiv_match = re.search(r'(\d+\.\d+)', paper['url'])
            if arxiv_match:
                arxiv_id = arxiv_match.group(1)
                paper['pdf_url'] = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                paper['arxiv_id'] = arxiv_id
        
        # 作者
        for key in ['authors', 'author']:
            if key in item:
                paper['authors'] = item[key]
                break
        
        # 日期
        paper['date'] = item.get('date', datetime.now().strftime('%Y-%m-%d'))
        
        return paper if paper.get('pdf_url') else None

    def _parse_nextjs_data(self, data):
        '''解析Next.js数据结构'''
        papers = []
        
        # 递归查找papers数据
        def find_papers(obj, depth=0):
            if depth > 10:  # 防止无限递归
                return []
            
            if isinstance(obj, dict):
                # 检查是否包含论文数据
                if 'papers' in obj:
                    return self._parse_api_response(obj)
                
                # 递归搜索
                for value in obj.values():
                    result = find_papers(value, depth + 1)
                    if result:
                        return result
                        
            elif isinstance(obj, list):
                # 检查是否是论文列表
                if obj and isinstance(obj[0], dict) and any(k in obj[0] for k in ['title', 'arxiv_id', 'paper_id']):
                    return self._parse_api_response(obj)
                
                # 递归搜索
                for item in obj:
                    result = find_papers(item, depth + 1)
                    if result:
                        return result
            
            return []
        
        papers = find_papers(data)
        return papers

    def _extract_papers_from_data(self, data):
        '''从任意数据结构中提取论文'''
        if isinstance(data, dict) and 'papers' in data:
            return self._parse_api_response(data['papers'])
        elif isinstance(data, list):
            return self._parse_api_response(data)
        else:
            return self._parse_nextjs_data(data)

    def download_papers(self, papers):
        '''下载论文PDF文件'''
        downloaded = []
        
        for i, paper in enumerate(papers):
            if not paper.get('pdf_url'):
                continue
            
            try:
                # 生成文件名
                arxiv_id = paper.get('arxiv_id', '').replace('/', '_')
                title = re.sub(r'[^\w\s-]', '', paper.get('title', 'untitled'))
                title = re.sub(r'[-\s]+', '-', title)[:100]  # 限制长度
                
                filename = f"{arxiv_id}_{title}.pdf" if arxiv_id else f"{title}.pdf"
                filepath = self.download_dir / filename
                
                # 检查是否已下载
                if filepath.exists():
                    self.logger.info(f"文件已存在，跳过: {filename}")
                    continue
                
                # 下载PDF
                self.logger.info(f"正在下载 ({i+1}/{len(papers)}): {paper['title']}")
                response = self._make_request(paper['pdf_url'], stream=True)
                
                if response and response.status_code == 200:
                    with open(filepath, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    self.logger.info(f"下载成功: {filename}")
                    downloaded.append({
                        'paper': paper,
                        'filepath': str(filepath)
                    })
                    
                    # 延迟，避免请求过快
                    time.sleep(self.delay)
                else:
                    self.logger.error(f"下载失败: {paper['title']}")
                    
            except Exception as e:
                self.logger.error(f"下载出错: {e}")
        
        return downloaded

    def run(self):
        '''主运行方法'''
        self.logger.info("开始获取HuggingFace Daily Papers...")
        
        # 获取论文列表
        papers = self.fetch_paper_list()
        
        if not papers:
            self.logger.warning("未能获取到任何论文")
            return
        
        self.logger.info(f"获取到 {len(papers)} 篇论文")
        
        # 下载论文
        if self.max_papers > 0:
            papers = papers[:self.max_papers]
            self.logger.info(f"根据配置，限制下载 {len(papers)} 篇")
        
        downloaded = self.download_papers(papers)
        
        # 保存状态
        state = {
            'last_run': datetime.now().isoformat(),
            'papers_found': len(papers),
            'papers_downloaded': len(downloaded),
            'downloaded_files': [d['filepath'] for d in downloaded]
        }
        
        state_file = self.state_dir / 'download_state.json'
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        
        self.logger.info(f"下载完成！共下载 {len(downloaded)} 篇论文")
        
        return downloaded


if __name__ == "__main__":
    # 测试代码
    import configparser
    
    # 创建测试配置
    config = configparser.ConfigParser()
    config['paths'] = {
        'download_dir': 'test_downloads',
        'state_dir': 'test_state'
    }
    config['huggingface'] = {
        'max_papers': '5',
        'request_timeout': '30',
        'retry_count': '3',
        'request_delay': '1.0'
    }
    
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 运行下载器
    downloader = HuggingFaceDownloader(config)
    downloader.run()
