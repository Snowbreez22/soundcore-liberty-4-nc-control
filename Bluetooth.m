#import <Foundation/Foundation.h>
#import <IOBluetooth/IOBluetooth.h>

@interface Link : NSObject <IOBluetoothRFCOMMChannelDelegate>
@property (nonatomic, strong) NSMutableData *bytes;
@property BOOL discoveryDone;
@property BOOL closed;
@end

@implementation Link
- (void)sdpQueryComplete:(IOBluetoothDevice *)device status:(IOReturn)status {
    self.discoveryDone = YES;
}
- (void)rfcommChannelData:(IOBluetoothRFCOMMChannel *)channel data:(void *)data length:(size_t)length {
    [self.bytes appendBytes:data length:length];
}
- (void)rfcommChannelClosed:(IOBluetoothRFCOMMChannel *)channel {
    self.closed = YES;
}
@end

static int fail(NSString *message) {
    fprintf(stderr, "%s\n", message.UTF8String);
    return 1;
}

static void pump(void) {
    [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.02]];
}

int main(void) {
    @autoreleasepool {
        NSMutableArray *candidates = [NSMutableArray array];
        for (IOBluetoothDevice *device in [IOBluetoothDevice pairedDevices]) {
            if ([device isConnected] &&
                [[device.name lowercaseString] containsString:@"liberty 4 nc"]) {
                [candidates addObject:device];
            }
        }
        if (candidates.count != 1) {
            return fail(@"Connect one Liberty 4 NC in macOS Bluetooth settings. If you renamed it, include Liberty 4 NC in its name.");
        }

        IOBluetoothDevice *device = candidates.firstObject;
        const UInt8 uuidBytes[] = {0x0c,0xf1,0x2d,0x31,0xfa,0xc3,0x45,0x53,0xbd,0x80,0xd6,0x83,0x2e,0x7b,0x39,0x47};
        IOBluetoothSDPUUID *uuid = [IOBluetoothSDPUUID uuidWithBytes:uuidBytes length:sizeof uuidBytes];
        Link *link = [Link new];
        link.bytes = [NSMutableData data];
        IOBluetoothSDPServiceRecord *record = [device getServiceRecordForUUID:uuid];
        if (!record && [device performSDPQuery:link uuids:@[uuid]] == kIOReturnSuccess) {
            double deadline = NSProcessInfo.processInfo.systemUptime + 4;
            while (!link.discoveryDone && NSProcessInfo.processInfo.systemUptime < deadline) pump();
            record = [device getServiceRecordForUUID:uuid];
        }

        BluetoothRFCOMMChannelID channelID = 0;
        if (!record || [record getRFCOMMChannelID:&channelID] != kIOReturnSuccess) {
            return fail(@"macOS could not find the Liberty 4 NC control service. Reconnect the earbuds and try again.");
        }

        IOBluetoothRFCOMMChannel *channel = nil;
        if ([device openRFCOMMChannelSync:&channel withChannelID:channelID delegate:link] != kIOReturnSuccess || !channel) {
            return fail(@"Could not open the earbuds’ control channel. Close the Soundcore app on your phone and try again.");
        }
        setvbuf(stdout, NULL, _IOLBF, 0);
        puts("READY");
        char line[1024];
        while (fgets(line, sizeof line, stdin)) {
            size_t size = strcspn(line, "\r\n");
            if (size < 20 || size > 512 || size % 2) break;
            UInt8 packet[256];
            for (size_t i = 0; i < size / 2; ++i) {
                unsigned int value;
                if (sscanf(line + 2*i, "%2x", &value) != 1) return fail(@"Invalid command.");
                packet[i] = value;
            }

            [link.bytes setLength:0];
            IOReturn result = [channel writeSync:packet length:(UInt16)(size / 2)];
            if (result != kIOReturnSuccess) {
                puts("-");
                break;
            }
            double deadline = NSProcessInfo.processInfo.systemUptime + 1.8;
            BOOL matched = NO;
            while (!link.closed && NSProcessInfo.processInfo.systemUptime < deadline) {
                pump();
                while (link.bytes.length >= 2) {
                    const UInt8 *p = link.bytes.bytes;
                    if (p[0] != 9 || p[1] != 255) {
                        [link.bytes replaceBytesInRange:NSMakeRange(0, 1) withBytes:NULL length:0];
                        continue;
                    }
                    if (link.bytes.length < 9) break;
                    size_t count = p[7] + 256*p[8];
                    if (count < 10 || count > 1024) {
                        [link.bytes replaceBytesInRange:NSMakeRange(0, 1) withBytes:NULL length:0];
                        continue;
                    }
                    if (link.bytes.length < count) break;
                    UInt8 sum = 0;
                    for (size_t i = 0; i + 1 < count; ++i) sum += p[i];
                    if (sum == p[count-1] && p[5] == packet[5] && p[6] == packet[6]) {
                        for (size_t i = 9; i + 1 < count; ++i) printf("%02x", p[i]);
                        puts("");
                        matched = YES;
                        break;
                    }
                    [link.bytes replaceBytesInRange:NSMakeRange(0, count) withBytes:NULL length:0];
                }
                if (matched) break;
            }
            if (!matched) puts("-");
            if (link.closed) break;
        }
        [channel closeChannel];
    }
    return 0;
}
