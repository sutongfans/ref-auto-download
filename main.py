#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
HuggingFace Daily Papers Scraper - Main Entry Point

This script serves as the main entry point for the HuggingFace daily papers scraper.
It reads configuration, sets up logging, and schedules the downloader to run at specified intervals.
"""

import os
import sys
import time
import logging
import configparser
import schedule
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from downloader import HuggingFaceDownloader


def setup_logging():
    """
    Set up logging configuration
    """
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / f"scraper_{datetime.now().strftime('%Y%m%d')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger("huggingface_scraper")


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


def run_scraper(logger, config):
    """
    Run the HuggingFace papers downloader
    """
    try:
        logger.info("Starting HuggingFace papers download task")
        
        # Create downloader instance
        downloader = HuggingFaceDownloader(config)
        
        # Run the download process
        downloader.download_daily_papers()
        
        logger.info("HuggingFace papers download task completed successfully")
    except Exception as e:
        logger.error(f"Error in scraper execution: {str(e)}", exc_info=True)


def main():
    """
    Main function to set up and run the scraper
    """
    # Setup logging
    logger = setup_logging()
    logger.info("HuggingFace Scraper starting up")
    
    try:
        # Load configuration
        config = load_config()
        logger.info("Configuration loaded successfully")
        
        # Get schedule time from config
        schedule_time = config.get("scheduler", "daily_run_time", fallback="00:00")
        logger.info(f"Scheduled to run daily at {schedule_time}")
        
        # Schedule the job
        schedule.every().day.at(schedule_time).do(run_scraper, logger=logger, config=config)
        
        # If run_immediately is set to True in config, run once at startup
        if config.getboolean("scheduler", "run_immediately", fallback=False):
            logger.info("Running scraper immediately as configured")
            run_scraper(logger, config)
        
        # Keep the script running
        logger.info("Entering scheduler loop")
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
            
    except KeyboardInterrupt:
        logger.info("Scraper shutting down due to keyboard interrupt")
    except Exception as e:
        logger.error(f"Unhandled exception in main: {str(e)}", exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
