#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
PDF Processor with Watchdog

This module monitors the downloaded_papers directory for new PDF files,
processes them by sending to the MCP service, and handles the results.
"""

import os
import sys
import time
import json
import logging
import requests
import configparser
from pathlib import Path
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class PDFProcessor:
    """
    Class for processing PDF files and interacting with MCP service
    """
    
    def __init__(self, config):
        """
        Initialize the processor with configuration
        
        Args:
            config: ConfigParser object with configuration settings
        """
        self.logger = logging.getLogger("huggingface_scraper.processor")
        self.config = config
        
        # MCP service URL
        self.mcp_url = config.get("mcp", "api_url", 
                                fallback="http://localhost:8000/process")
        
        # Request timeout in seconds
        self.timeout = config.getint("mcp", "request_timeout", fallback=60)
        
        # Directory to monitor for new PDFs
        self.download_dir = Path(config.get("paths", "download_dir", 
                                          fallback="downloaded_papers"))
        
        # Create directory if it doesn't exist
        self.download_dir.mkdir(exist_ok=True, parents=True)
        
        # Processed files tracking
        self.processed_files_path = Path(config.get("paths", "state_dir", 
                                                 fallback="state")) / "processed_files.json"
        self.processed_files = self._load_processed_files()
    
    def _load_processed_files(self):
        """
        Load the list of already processed files
        
        Returns:
            dict: Dictionary of processed files with paths as keys
        """
        if self.processed_files_path.exists():
            try:
                with open(self.processed_files_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                self.logger.error("Invalid processed files format, creating new one")
        
        # Create directory if it doesn't exist
        self.processed_files_path.parent.mkdir(exist_ok=True, parents=True)
        return {}
    
    def _save_processed_files(self):
        """
        Save the list of processed files
        """
        with open(self.processed_files_path, "w", encoding="utf-8") as f:
            json.dump(self.processed_files, f, indent=2)
    
    def process_pdf(self, pdf_path):
        """
        Process a PDF file by sending it to the MCP service
        
        Args:
            pdf_path (Path): Path to the PDF file
            
        Returns:
            dict: Processing result from MCP service or None if failed
        """
        if str(pdf_path) in self.processed_files:
            self.logger.info(f"Skipping already processed file: {pdf_path}")
            return None
        
        self.logger.info(f"Processing PDF: {pdf_path}")
        
        # Check if the file exists and is a PDF
        if not pdf_path.exists() or pdf_path.suffix.lower() != ".pdf":
            self.logger.error(f"Invalid PDF file: {pdf_path}")
            return None
        
        # Get metadata if available
        metadata = {}
        metadata_path = pdf_path.with_suffix(".json")
        if metadata_path.exists():
            try:
                with open(metadata_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
            except json.JSONDecodeError:
                self.logger.warning(f"Invalid metadata format for {pdf_path}")
        
        try:
            # Log the processing step
            self.logger.info(f"Sending PDF to MCP service: {self.mcp_url}")
            
            # Prepare the files and data for the request
            files = {
                'pdf': (pdf_path.name, open(pdf_path, 'rb'), 'application/pdf')
            }
            
            data = {
                'metadata': json.dumps(metadata)
            }
            
            # Send the request to MCP service
            response = requests.post(
                self.mcp_url,
                files=files,
                data=data,
                timeout=self.timeout
            )
            
            # Close the file
            files['pdf'][1].close()
            
            # Check if the request was successful
            response.raise_for_status()
            
            # Parse the response
            result = response.json()
            
            # Mark the file as processed
            self.processed_files[str(pdf_path)] = {
                "processed_at": datetime.now().isoformat(),
                "result": result
            }
            self._save_processed_files()
            
            # Log success
            self.logger.info(f"Successfully processed {pdf_path}")
            
            # Print the result to stdout for downstream use
            print(json.dumps(result, indent=2))
            
            return result
            
        except requests.RequestException as e:
            self.logger.error(f"Error communicating with MCP service: {str(e)}")
            return None
        except Exception as e:
            self.logger.error(f"Error processing {pdf_path}: {str(e)}")
            return None


class PDFHandler(FileSystemEventHandler):
    """
    Handler for file system events on PDF files
    """
    
    def __init__(self, processor):
        """
        Initialize the handler with a processor
        
        Args:
            processor (PDFProcessor): The processor to use for PDFs
        """
        self.processor = processor
        self.logger = logging.getLogger("huggingface_scraper.processor.handler")
    
    def on_created(self, event):
        """
        Handle file creation events
        
        Args:
            event: The file system event
        """
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        
        # Only process PDF files
        if file_path.suffix.lower() == ".pdf":
            self.logger.info(f"New PDF detected: {file_path}")
            
            # Wait a moment to ensure the file is completely written
            time.sleep(1)
            
            # Call the on_new_file_created function to handle the new file
            self.on_new_file_created(event)
    
    def on_new_file_created(self, event):
        """
        Handle new file creation events specifically for PDFs
        
        Args:
            event: The file system event
        """
        file_path = event.src_path
        if file_path.endswith('.pdf'):
            try:
                self.logger.info(f"Sending PDF to MCP service: {file_path}")
                response = requests.post(
                    f"{self.processor.mcp_url}/process_pdf", 
                    json={"file_path": file_path},
                    timeout=self.processor.timeout
                )
                response.raise_for_status()
                self.logger.info(f"Successfully sent {file_path} to MCP service")
                
                # Mark as processed in the processor
                self.processor.processed_files[str(file_path)] = {
                    "processed_at": datetime.now().isoformat(),
                    "sent_to_mcp": True
                }
                self.processor._save_processed_files()
                
            except Exception as e:
                self.logger.error(f"调用MCP服务失败: {e}")
        else:
            # Process non-PDF files if needed
            pass


def setup_logging():
    """
    Set up logging configuration
    """
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / f"processor_{datetime.now().strftime('%Y%m%d')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger("huggingface_scraper.processor")


def load_config():
    """
    Load configuration from config.ini
    """
    config = configparser.ConfigParser()
    config_path = Path(__file__).parent / "config.ini"
    
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    config.read(config_path)
    return config


def process_existing_pdfs(processor, directory):
    """
    Process existing PDF files in the directory
    
    Args:
        processor (PDFProcessor): The processor to use
        directory (Path): The directory to scan
    """
    logger = logging.getLogger("huggingface_scraper.processor")
    logger.info(f"Scanning for existing PDFs in {directory}")
    
    # Scan for PDF files recursively
    pdf_files = list(directory.glob("**/*.pdf"))
    logger.info(f"Found {len(pdf_files)} existing PDF files")
    
    # Process each PDF
    for pdf_path in pdf_files:
        processor.process_pdf(pdf_path)


def main():
    """
    Main function to set up and run the processor
    """
    # Setup logging
    logger = setup_logging()
    logger.info("PDF Processor starting up")
    
    try:
        # Load configuration
        config = load_config()
        logger.info("Configuration loaded successfully")
        
        # Create processor
        processor = PDFProcessor(config)
        
        # Process existing PDFs if configured
        if config.getboolean("processor", "process_existing", fallback=True):
            process_existing_pdfs(processor, processor.download_dir)
        
        # Set up watchdog observer
        event_handler = PDFHandler(processor)
        observer = Observer()
        
        # Start watching the download directory
        observer.schedule(event_handler, str(processor.download_dir), recursive=True)
        observer.start()
        logger.info(f"Watching for new PDFs in {processor.download_dir}")
        
        # Keep the script running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
            logger.info("Processor shutting down due to keyboard interrupt")
        
        observer.join()
        
    except Exception as e:
        logger.error(f"Unhandled exception in main: {str(e)}", exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
