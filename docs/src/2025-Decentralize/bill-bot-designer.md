# Bill Bot Designer

## Overview

The Bill Bot Designer is a tool for creating automated bots that monitor and publish legislative updates from the Open Civic Data Blockchain. These bots can be configured to watch specific bills, jurisdictions, or events and automatically post updates to various platforms like Bluesky, Twitter, RSS feeds, or custom webhooks.

## Why Bots?

- 🤖 **Automated Monitoring**: Bots can continuously watch for legislative changes without human intervention
- 📢 **Multi-Platform Publishing**: Single bot configuration can publish to multiple platforms simultaneously
- 🎯 **Targeted Alerts**: Organizations can create highly specific feeds for their constituents
- ⚡ **Real-Time Updates**: Instant notifications when important legislative events occur
- 🔄 **Consistent Formatting**: Standardized message formats across all platforms

## Bot Architecture

### Event-Driven Design

Bots operate on an event-driven architecture, listening to the append-only log of legislative events:

```
Legislative Event → Blockchain Log → Bot Filter → Message Generation → Platform Publishing
```

### Bot Components

1. **Event Listener**: Monitors the blockchain log for new events
2. **Filter Engine**: Applies rules to determine if an event should trigger the bot
3. **Message Generator**: Creates platform-specific messages from event data
4. **Publisher**: Sends messages to configured platforms
5. **Rate Limiter**: Ensures compliance with platform API limits

## Configuration Examples

### Basic Bill Monitor Bot

```yaml
name: "Illinois Bill Monitor"
description: "Monitors all Illinois bills for key actions"

# Event filtering
filters:
  - jurisdiction: "country:us/state:il"
  - event_types: ["bill_introduced", "bill_passed", "bill_vetoed"]
  - keywords: ["environment", "education", "healthcare"]

# Message template
message_template: |
  📋 {bill.identifier}: {bill.title}
  🏛️ {action.description}
  📅 {action.date}
  🔗 {bill.url}

# Publishing platforms
platforms:
  - type: "bluesky"
    account: "@legislative-alerts.bsky.social"
    rate_limit: "10/hour"
  
  - type: "rss"
    feed_url: "https://example.com/il-bills.xml"
    update_frequency: "immediate"
```

### Specialized Committee Bot

```yaml
name: "Senate Appropriations Monitor"
description: "Tracks all bills going through Senate Appropriations"

filters:
  - jurisdiction: "country:us/state:il"
  - committee: "Senate Appropriations"
  - event_types: ["bill_referred", "bill_hearing_scheduled", "bill_vote"]

message_template: |
  💰 Senate Appropriations Update
  📋 {bill.identifier}: {bill.title}
  📊 Fiscal Impact: {bill.fiscal_note.summary}
  📅 Next Action: {next_action.description}
  🗓️ Date: {next_action.date}

platforms:
  - type: "webhook"
    url: "https://api.example.com/appropriations-webhook"
    headers:
      Authorization: "Bearer {webhook_token}"
  
  - type: "email"
    recipients: ["budget@example.org", "finance@example.org"]
    subject: "Senate Appropriations Alert: {bill.identifier}"
```

### Constituent Alert Bot

```yaml
name: "District 5 Constituent Alerts"
description: "Alerts constituents about bills affecting their district"

filters:
  - jurisdiction: "country:us/state:il"
  - sponsor_district: "5"
  - event_types: ["bill_introduced", "bill_passed", "bill_signed"]

message_template: |
  🏠 District 5 Update
  📋 {bill.identifier}: {bill.title}
  👤 Sponsored by: {sponsor.name}
  📝 Summary: {bill.summary}
  📅 Status: {bill.status}
  🔗 Learn more: {bill.url}

platforms:
  - type: "sms"
    phone_numbers: ["+15551234567", "+15559876543"]
    provider: "twilio"
  
  - type: "slack"
    channel: "#district-5-alerts"
    workspace: "example-org"
```

## Platform Integrations

### Bluesky
- **Rate Limit**: 10 posts per hour
- **Character Limit**: 300 characters
- **Features**: Rich text, links, images
- **Authentication**: App password required

### Twitter/X
- **Rate Limit**: 300 tweets per 3 hours
- **Character Limit**: 280 characters
- **Features**: Text, images, polls
- **Authentication**: OAuth 2.0

### RSS Feeds
- **Format**: RSS 2.0 or Atom
- **Update Frequency**: Configurable
- **Features**: Full text, categories, enclosures
- **Hosting**: GitHub Pages, custom server

### Webhooks
- **Method**: POST
- **Content-Type**: application/json
- **Authentication**: Bearer token or API key
- **Retry Logic**: Exponential backoff

### Email
- **Providers**: SMTP, SendGrid, Mailgun
- **Templates**: HTML and plain text
- **Attachments**: PDF bills, documents
- **Rate Limits**: Varies by provider

### SMS
- **Providers**: Twilio, AWS SNS
- **Character Limit**: 160 characters
- **Features**: Text only
- **Cost**: Per message

## Advanced Features

### Conditional Logic

```yaml
filters:
  - jurisdiction: "country:us/state:il"
  - conditions:
      - if: "bill.fiscal_impact > 1000000"
        then: "priority = high"
      - if: "bill.sponsor.party == 'Republican'"
        then: "include_opposition_analysis = true"
```

### Message Templates with Variables

```yaml
message_template: |
  {#if bill.fiscal_impact > 1000000}💰 HIGH COST BILL {/if}
  📋 {bill.identifier}: {bill.title}
  👤 Sponsor: {bill.sponsors[0].name} ({bill.sponsors[0].party})
  📊 Fiscal Impact: ${bill.fiscal_impact:,.0f}
  📅 {action.date | date_format: "%B %d, %Y"}
  🔗 {bill.url}
  
  {#if bill.summary}
  📝 {bill.summary | truncate: 200}
  {/if}
```

### Scheduled Publishing

```yaml
publishing:
  schedule:
    - time: "09:00"
      timezone: "America/Chicago"
      days: ["monday", "tuesday", "wednesday", "thursday", "friday"]
    - time: "17:00"
      timezone: "America/Chicago"
      days: ["monday", "tuesday", "wednesday", "thursday", "friday"]
  
  batch_size: 5
  delay_between_posts: "30s"
```

### Analytics and Monitoring

```yaml
analytics:
  track_engagement: true
  platforms:
    - bluesky
    - twitter
    - webhook
  
  metrics:
    - posts_sent
    - engagement_rate
    - error_rate
    - response_time
  
  alerts:
    - condition: "error_rate > 0.05"
      action: "email_admin"
    - condition: "no_posts_24h"
      action: "slack_alert"
```

## Best Practices

### Content Guidelines

1. **Be Accurate**: Always verify data before publishing
2. **Stay Neutral**: Present information without bias
3. **Include Context**: Provide background information when relevant
4. **Use Clear Language**: Avoid jargon and technical terms
5. **Include Sources**: Always link to official sources

### Technical Guidelines

1. **Rate Limiting**: Respect platform API limits
2. **Error Handling**: Implement retry logic and fallbacks
3. **Monitoring**: Track bot performance and errors
4. **Testing**: Test configurations before going live
5. **Documentation**: Document bot purposes and configurations

### Legal Considerations

1. **Copyright**: Respect copyright on bill text and documents
2. **Attribution**: Always credit original sources
3. **Disclaimers**: Include appropriate disclaimers
4. **Compliance**: Follow platform terms of service
5. **Privacy**: Don't collect or store personal information

## Getting Started

### 1. Choose Your Use Case

- **General Monitoring**: Track all bills in a jurisdiction
- **Committee Focus**: Monitor specific committees
- **Issue-Based**: Track bills by topic or keywords
- **Constituent Service**: Alert constituents about relevant bills

### 2. Design Your Filters

- **Jurisdiction**: Which government body to monitor
- **Event Types**: What actions to track
- **Keywords**: Specific topics or terms
- **Sponsors**: Bills from specific legislators

### 3. Create Your Message Template

- **Platform Limits**: Consider character limits
- **Required Information**: Bill ID, title, action, date
- **Optional Details**: Sponsor, summary, fiscal impact
- **Call to Action**: Links to learn more or take action

### 4. Configure Platforms

- **Primary Platform**: Choose your main publishing platform
- **Secondary Platforms**: Add additional platforms for reach
- **Testing**: Test with a small audience first
- **Monitoring**: Set up alerts and analytics

### 5. Deploy and Monitor

- **Gradual Rollout**: Start with limited scope
- **Monitor Performance**: Track engagement and errors
- **Iterate**: Refine based on feedback and data
- **Scale**: Expand to additional jurisdictions or topics

## Examples in Action

### Bluesky Legislative Alerts

The [Bluesky LGBTQ+ Legislation Alerts](https://bsky.app/profile/legialerts.org) bot demonstrates how effective automated legislative monitoring can be. It:

- Monitors bills across multiple states
- Filters for LGBTQ+ related legislation
- Posts concise, informative updates
- Builds a community around legislative transparency

### Chicago Councilmatic

The Chicago Councilmatic system shows how bots can enhance existing civic data platforms:

- Integrates with existing Open Civic Data sources
- Provides real-time updates on city council activities
- Maintains historical records of all legislative actions
- Enables custom feeds for different stakeholders

## Future Enhancements

### AI-Powered Features

- **Smart Summaries**: AI-generated bill summaries
- **Impact Analysis**: Automated analysis of bill effects
- **Sentiment Analysis**: Track public opinion on bills
- **Predictive Modeling**: Forecast bill outcomes

### Advanced Integrations

- **Calendar Integration**: Add events to personal calendars
- **CRM Integration**: Track constituent interactions
- **Newsletter Integration**: Compile weekly summaries
- **API Access**: Allow third-party integrations

### Enhanced Analytics

- **Engagement Tracking**: Measure bot effectiveness
- **A/B Testing**: Test different message formats
- **Audience Insights**: Understand who's following bots
- **Performance Optimization**: Improve delivery rates